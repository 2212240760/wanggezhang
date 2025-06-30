import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import sqlite3
from io import BytesIO
from datetime import datetime, timedelta
import shutil
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# 确保数据库目录存在
db_dir = "data"
os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, "grid_assessment.db")

# 加载用户认证配置
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

name, authentication_status, username = authenticator.login('登录', 'main')

if authentication_status:
    authenticator.logout('退出登录', 'main')
    st.write(f'欢迎 *{name}*')

    def get_db_connection():
        """获取数据库连接，添加异常处理"""
        try:
            conn = sqlite3.connect(db_path)
            # 确保中文显示正常
            conn.text_factory = str
            return conn
        except Exception as e:
            st.error(f"无法连接到数据库: {e}")
            return None

    def validate_score(score):
        """验证分数是否有效"""
        try:
            score = float(score)
            return 0 <= score <= 100
        except (ValueError, TypeError):
            return False

    def update_assessment(assessment_id, scores):
        """更新评估数据"""
        conn = get_db_connection()
        if conn is None:
            return False
        
        try:
            cursor = conn.cursor()
            # 构建SQL更新语句
            set_clauses = ", ".join([f"{dim_to_db_col[dim]} = ?" for dim in DIMENSIONS])
            values = [scores[dim] for dim in DIMENSIONS] + [assessment_id]
            
            sql = f"UPDATE assessments SET {set_clauses} WHERE id = ?"
            cursor.execute(sql, values)
            conn.commit()
            return True
        except Exception as e:
            st.error(f"更新评估数据失败: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def get_leader_assessments(leader_id):
        """获取网格长评估数据"""
        conn = get_db_connection()
        if conn is None:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM assessments WHERE leader_id = ? ORDER BY date DESC",
                (leader_id,)
            )
            columns = [col[0] for col in cursor.description]
            # 确保将查询结果转换为字典，避免使用元组索引
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            st.error(f"获取评估数据失败: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def handle_none_scores(scores, dimensions):
        """处理分数中的None值，确保所有维度都有值"""
        for dim in dimensions:
            if dim not in scores or scores[dim] is None:
                scores[dim] = 0
        return scores

    def calculate_total_score(scores, weights, dimensions):
        """计算综合得分"""
        total = 0
        for dim in dimensions:
            total += scores.get(dim, 0) * weights[dim]
        return total

    def get_all_leaders(refresh=False):
        """获取所有网格长，支持强制刷新缓存"""
        conn = get_db_connection()
        if conn is None:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grid_leaders")
            columns = [col[0] for col in cursor.description]
            leaders = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # 强制刷新时更新缓存
            if refresh:
                st.session_state.all_leaders = leaders
            return leaders
        except Exception as e:
            st.error(f"获取网格长列表失败: {e}")
            return []
        finally:
            if conn:
                conn.close()

    # 能力维度配置
    DIMENSIONS = [
        "专业技术能力", "指标掌控能力", "管理执行能力", "沟通协调能力", "市场营销能力",
        "超长工单占比", "催单率", "上门及时率", "重复投诉率", "万投比",
        "触点服务客户满意占比", "质差客户占比", "家宽单用户中断时长", "家宽弱光率",
        "任务工单支撑及时率", "交班交底率", "终端盘点", "人员达标率",
        "低销占比", "商机转化率", "元宝完成率", "终端收入"
    ]
    
    # 定义数据库字段映射
    db_columns = [
        "professional_skill", "index_mastery", "management_execution", "communication_coordination", "marketing_ability",
        "long_work_order_ratio", "reminder_rate", "on_site_timeliness", "repeat_complaint_rate", "complaints_per_ten_thousand",
        "contact_service_satisfaction", "poor_quality_customer_ratio", "home_broadband_interrupt_duration", "home_broadband_weak_light_rate",
        "task_support_timeliness", "handover_rate", "terminal_inventory", "personnel_qualified_rate",
        "low_sales_ratio", "business_opportunity_conversion_rate", "yuanbao_completion_rate", "terminal_revenue"
    ]
    
    # 创建维度到数据库列的映射
    dim_to_db_col = {dim: db_col for dim, db_col in zip(DIMENSIONS, db_columns)}
    WEIGHTS = {dim: 1/len(DIMENSIONS) for dim in DIMENSIONS}
    THRESHOLDS = {
        "优秀": 85,
        "良好": 75,
        "合格": 60
    }
    
    IMPROVEMENT_TIPS = {
        "专业技术能力": ["加强专业技能培训", "参与技术交流活动", "考取相关专业证书"],
        "指标掌控能力": ["深入理解业务指标体系", "定期分析指标数据", "制定针对性提升计划"],
        "管理执行能力": ["优化工作流程", "加强团队协作", "提高执行力和决策力"],
        "沟通协调能力": ["加强团队沟通", "提高跨部门协作能力", "提升客户沟通技巧"],
        "市场营销能力": ["学习市场营销知识", "分析市场趋势", "提高客户开发能力"],
        "超长工单占比": ["优化工单处理流程", "提高工单处理效率", "加强工单跟踪管理"],
        "催单率": ["提高服务质量", "及时响应客户需求", "优化服务流程"],
        "上门及时率": ["合理安排上门服务时间", "加强服务人员管理", "提高服务效率"],
        "重复投诉率": ["提高问题解决能力", "加强服务质量监督", "建立客户反馈机制"],
        "万投比": ["提高服务质量", "加强客户关系管理", "优化服务流程"],
        "触点服务客户满意占比": ["提高服务态度", "加强服务技能培训", "建立客户反馈机制"],
        "质差客户占比": ["提高服务质量", "加强网络维护", "优化网络质量"],
        "家宽单用户中断时长": ["加强网络维护", "提高故障处理效率", "优化网络结构"],
        "家宽弱光率": ["加强线路维护", "优化光路质量", "提高设备性能"],
        "任务工单支撑及时率": ["加强团队协作", "提高工作效率", "优化任务分配"],
        "交班交底率": ["建立规范的交接班制度", "加强交接班管理", "提高工作responsibility"],
        "终端盘点": ["建立完善的终端管理制度", "定期进行终端盘点", "提高资产管理水平"],
        "人员达标率": ["加强人员培训", "建立考核机制", "提高人员素质"],
        "低销占比": ["加强市场调研", "优化产品结构", "提高销售能力"],
        "商机转化率": ["加强市场分析", "优化销售策略", "提高销售技巧"],
        "元宝完成率": ["明确目标任务", "制定合理计划", "加强过程管理"],
        "终端收入": ["优化产品结构", "提高销售能力", "加强客户关系管理"]
    }
    
    # 初始化数据库
    def init_database():
        conn = get_db_connection()
        if conn is None:
            return
        
        try:
            cursor = conn.cursor()
            
            # 创建网格长表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS grid_leaders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                area TEXT NOT NULL
            )
            ''')
            
            # 创建评估表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                leader_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                professional_skill REAL,
                index_mastery REAL,
                management_execution REAL,
                communication_coordination REAL,
                marketing_ability REAL,
                long_work_order_ratio REAL,
                reminder_rate REAL,
                on_site_timeliness REAL,
                repeat_complaint_rate REAL,
                complaints_per_ten_thousand REAL,
                contact_service_satisfaction REAL,
                poor_quality_customer_ratio REAL,
                home_broadband_interrupt_duration REAL,
                home_broadband_weak_light_rate REAL,
                task_support_timeliness REAL,
                handover_rate REAL,
                terminal_inventory REAL,
                personnel_qualified_rate REAL,
                low_sales_ratio REAL,
                business_opportunity_conversion_rate REAL,
                yuanbao_completion_rate REAL,
                terminal_revenue REAL,
                import_date TEXT,
                FOREIGN KEY (leader_id) REFERENCES grid_leaders (id)
            )
            ''')
            
            conn.commit()
            st.success("数据库初始化成功！")
            st.session_state.database_initialized = True
        except Exception as e:
            st.error(f"数据库初始化失败: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def import_data(file):
        """导入数据时支持列名映射，解决缺少必要列的问题"""
        if file.name.endswith('.csv'):
            # 读取文件内容，检查是否为空
            content = file.read().decode('utf-8', errors='ignore')
            if not content.strip():
                st.error("上传的 CSV 文件为空，请检查文件内容。")
                return False
            file.seek(0)  # 将文件指针重置到文件开头
            try:
                # 先尝试使用 UTF-8 编码
                df = pd.read_csv(file, encoding='utf-8', skipinitialspace=True, skip_blank_lines=True)
            except UnicodeDecodeError:
                file.seek(0)  # 重置文件指针
                try:
                    # 若 UTF-8 失败，尝试 GBK 编码
                    df = pd.read_csv(file, encoding='gbk', skipinitialspace=True, skip_blank_lines=True)
                except UnicodeDecodeError:
                    file.seek(0)  # 重置文件指针
                    try:
                        # 若 GBK 失败，尝试 GB2312 编码
                        df = pd.read_csv(file, encoding='gb2312', skipinitialspace=True, skip_blank_lines=True)
                    except UnicodeDecodeError:
                        st.error("无法识别文件编码，请确保文件编码为 UTF-8、GBK 或 GB2312。")
                        return False
        elif file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            st.error("不支持的文件格式，请上传 xlsx、xls 或 csv 文件。")
            return False
        
        # 检查 DataFrame 是否为空
        if df.empty:
            st.error("上传的文件为空或无法解析出有效数据，请检查文件内容。")
            return False
        
        # 显示文件前几行供用户确认
        st.subheader("文件数据预览")
        st.write(df.head())
        
        # 定义必须的列（程序所需的字段）
        required_fields = ['name', 'area', 'date'] + list(dim_to_db_col.values())
        
        # 获取文件中的列名
        file_columns = df.columns.tolist()
        
        # 列名映射设置界面
        st.subheader("列名映射设置")
        st.info("请将文件中的列映射到系统所需的字段，未映射的字段将设为0")
        
        # 映射必须的字段：name, area, date
        mapped_fields = {}
        
        # 映射 name 列
        st.write("### 基本信息映射")
        name_options = ['无匹配列'] + file_columns
        mapped_fields['name'] = st.selectbox("映射到 '姓名' 字段", name_options, key="map_name")
        
        # 映射 area 列
        area_options = ['无匹配列'] + file_columns
        mapped_fields['area'] = st.selectbox("映射到 '辖区' 字段", area_options, key="map_area")
        
        # 映射 date 列
        date_options = ['无匹配列'] + file_columns
        mapped_fields['date'] = st.selectbox("映射到 '评估日期' 字段", date_options, key="map_date")
        
        # 映射评估维度列
        st.write("### 能力评估维度映射")
        for dim, db_col in dim_to_db_col.items():
            col_options = ['无匹配列（设为0）'] + file_columns
            mapped_fields[db_col] = st.selectbox(f"映射到 '{dim}' 字段", col_options, key=f"map_{db_col}")
        
        # 确认映射
        if 'confirm_import' not in st.session_state:
            st.session_state.confirm_import = False
        
        if st.button("确认映射并导入", key="confirm_import_button"):
            st.session_state.confirm_import = True
        
        if st.session_state.confirm_import:
            # 检查基本信息是否有映射
            if mapped_fields['name'] == '无匹配列' or mapped_fields['area'] == '无匹配列' or mapped_fields['date'] == '无匹配列':
                st.error("姓名、辖区和评估日期必须映射有效列！")
                st.session_state.confirm_import = False
                return False
            
            # 准备导入数据
            conn = get_db_connection()
            if conn is None:
                st.session_state.confirm_import = False
                return False
            
            try:
                with conn:  # 使用上下文管理器自动管理事务
                    cursor = conn.cursor()
                    # 导入网格长数据（去重处理）
                    leaders_data = df.drop_duplicates(subset=[mapped_fields['name'], mapped_fields['area']])
                    for _, row in leaders_data.iterrows():
                        leader_name = row[mapped_fields['name']]
                        leader_area = row[mapped_fields['area']]
                        cursor.execute("INSERT OR IGNORE INTO grid_leaders (name, area) VALUES (?, ?)", (leader_name, leader_area))
                
                    # 导入评估数据，记录导入日期
                    import_date = datetime.now().strftime('%Y/%m/%d')
                    assessment_data = df.copy()
                    
                    # 处理评估维度数据
                    for db_col in dim_to_db_col.values():
                        file_col = mapped_fields[db_col]
                        if file_col != '无匹配列（设为0）':
                            # 使用映射的列
                            assessment_data[db_col] = assessment_data[file_col]
                        else:
                            # 无匹配列，设为0
                            assessment_data[db_col] = 0
                    
                    # 批量导入评估数据
                    for _, row in assessment_data.iterrows():
                        # 查找网格长ID
                        leader_name = row[mapped_fields['name']]
                        cursor.execute("SELECT id FROM grid_leaders WHERE name = ?", (leader_name,))
                        leader = cursor.fetchone()
                        if leader:
                            leader_id = leader[0]
                            # 处理日期格式
                            try:
                                # 尝试解析多种可能的日期格式
                                date_str = str(row[mapped_fields['date']])
                                if ' ' in date_str:
                                    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                else:
                                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                                date_value = date_obj.strftime('%Y/%m/%d')
                            except ValueError:
                                st.error(f"日期格式错误: {row[mapped_fields['date']]}，请使用 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS' 格式。")
                                st.session_state.confirm_import = False
                                return False
                            
                            values = [
                                leader_id, date_value
                            ] + [row[db_col] for db_col in dim_to_db_col.values()] + [import_date]
                            
                            columns = "leader_id, date, " + ", ".join(dim_to_db_col.values()) + ", import_date"
                            placeholders = ", ".join(["?"] * (len(dim_to_db_col) + 3))
                            cursor.execute(f"INSERT INTO assessments ({columns}) VALUES ({placeholders})", values)
                    
                    # 强制刷新网格长列表缓存
                    get_all_leaders(refresh=True)
                    st.success(f"成功导入 {len(leaders_data)} 条网格长数据和 {len(assessment_data)} 条评估数据")
                    st.session_state.confirm_import = False
                    return True
            except Exception as e:
                st.error(f"数据导入失败: {str(e)}")
                st.session_state.confirm_import = False
                return False
            finally:
                if conn:
                    conn.close()

    def export_assessment_data(leader_id=None):
        """导出评估数据为 DataFrame，支持指定网格长或全部"""
        conn = get_db_connection()
        if conn is None:
            return pd.DataFrame()
        try:
            cursor = conn.cursor()
            if leader_id is not None:
                cursor.execute(
                    "SELECT a.*, g.name, g.area FROM assessments a LEFT JOIN grid_leaders g ON a.leader_id = g.id WHERE a.leader_id = ? ORDER BY a.date DESC",
                    (leader_id,)
                )
            else:
                cursor.execute(
                    "SELECT a.*, g.name, g.area FROM assessments a LEFT JOIN grid_leaders g ON a.leader_id = g.id ORDER BY a.date DESC"
                )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            return df
        except Exception as e:
            st.error(f"导出数据失败: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def clear_expired_data(days=30):
        """清理超过指定天数的评估数据"""
        conn = get_db_connection()
        if conn is None:
            return False
        
        try:
            cursor = conn.cursor()
            expired_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
            cursor.execute("DELETE FROM assessments WHERE import_date < ?", (expired_date,))
            conn.commit()
            return True
        except Exception as e:
            st.error(f"清理过期数据失败: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def to_excel(df):
        """将 DataFrame 导出为 Excel 文件的二进制流"""
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return output.getvalue()

    def clear_data():
        """清空所有评估数据和网格长数据"""
        conn = get_db_connection()
        if conn is None:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM assessments")
            cursor.execute("DELETE FROM grid_leaders")
            conn.commit()
            # 清空缓存
            if 'all_leaders' in st.session_state:
                del st.session_state.all_leaders
            st.success("所有数据已成功清空！")
            return True
        except Exception as e:
            st.error(f"清空数据失败: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def backup_database():
        """备份数据库"""
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"grid_assessment_{datetime.now().strftime('%Y%m%d%H%M%S')}.db")
        try:
            shutil.copy2(db_path, backup_file)
            st.info(f"数据库备份成功，备份文件路径: {backup_file}")
            return True
        except Exception as e:
            st.error(f"数据库备份失败: {e}")
            return False

    # 页面标题和配置
    st.set_page_config(
        page_title="网格长评估系统",
        page_icon="📊",
        layout="wide"
    )
    st.title("网格长能力评估系统")
    
    # 初始化会话状态
    if 'all_leaders' not in st.session_state:
        st.session_state.all_leaders = get_all_leaders()
    
    # 侧边栏
    with st.sidebar:
        # 手动初始化数据库按钮
        if st.button("手动初始化数据库", key="init_db_button"):
            init_database()
            # 初始化成功后检查并清理过期数据
            if st.session_state.get('database_initialized', False):
                clear_expired_data()
            # 刷新网格长列表
            st.session_state.all_leaders = get_all_leaders(refresh=True)
        
        st.header("选择评估周期")
        selected_date = st.selectbox(
            "选择评估日期",
            ["2025年6月", "2025年5月", "2025年4月", "2025年3月"]
        )
        
        st.header("选择网格长")
        all_leaders = st.session_state.all_leaders
        leader_names = [leader["name"] for leader in all_leaders]
        
        # 处理无网格长数据的情况
        if not leader_names:
            st.warning("暂无网格长数据，已添加示例数据")
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    # 添加示例网格长
                    cursor.execute("INSERT OR IGNORE INTO grid_leaders (name, area) VALUES (?, ?)", ("示例网格长", "示例区域"))
                    conn.commit()
                    # 刷新缓存
                    st.session_state.all_leaders = get_all_leaders(refresh=True)
                    all_leaders = st.session_state.all_leaders
                    leader_names = [leader["name"] for leader in all_leaders]
                except Exception as e:
                    st.error(f"添加示例数据失败: {e}")
                finally:
                    conn.close()
        
        # 确保下拉菜单使用最新的 leader_names，并处理选择逻辑
        if 'selected_name' not in st.session_state or st.session_state.selected_name not in leader_names:
            st.session_state.selected_name = leader_names[0] if leader_names else None
        
        selected_name = st.selectbox(
            "选择网格长姓名",
            leader_names,
            index=leader_names.index(st.session_state.selected_name) if st.session_state.selected_name in leader_names else 0,
            key="leader_selectbox"
        )
        st.session_state.selected_name = selected_name
        
        # 数据导入模块
        st.header("数据导入")
        uploaded_file = st.file_uploader(
            "上传 xlsx、xls 或 CSV 文件", 
            type=["xlsx", "xls", "csv"],
            key="file_uploader"
        )
        
        if uploaded_file is not None:
            import_data(uploaded_file)
        
        # 数据导出模块
        st.header("数据导出")
        export_format = st.selectbox("选择导出格式", ["CSV", "Excel"])
        export_scope = st.selectbox("选择导出范围", ["指定网格长", "所有网格长"])
        
        if export_scope == "指定网格长":
            selected_leader = next((leader for leader in all_leaders if leader["name"] == selected_name), None)
            if selected_leader:
                leader_id = selected_leader["id"]
            else:
                leader_id = None
        else:
            leader_id = None
        
        # 导出数据按钮
        if st.button("导出数据", key="export_data_button"):
            df = export_assessment_data(leader_id)
            if df is not None and not df.empty:
                if export_format == "CSV":
                    csv = df.to_csv(sep='\t', na_rep='nan')
                    st.download_button(
                        label="下载 CSV 文件",
                        data=csv,
                        file_name="assessment_data.csv",
                        mime="text/csv"
                    )
                elif export_format == "Excel":
                    excel_file = to_excel(df)
                    st.download_button(
                        label="下载 Excel 文件",
                        data=excel_file,
                        file_name="assessment_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.warning("没有可导出的数据。")
        
        # 数据清理模块
        st.header("数据清理")
        retention_days = st.number_input("保留数据天数", min_value=1, value=30)
        if st.button("清理过期数据", key="clear_expired_data_button"):
            if clear_expired_data(retention_days):
                st.success(f"成功清理超过 {retention_days} 天的评估数据！")
                # 刷新评估数据
                if 'selected_leader' in st.session_state:
                    st.session_state.selected_leader = None
            else:
                st.error("清理过期数据失败，请重试。")
        
        if st.button("清空所有数据", key="clear_all_data_button"):
            if clear_data():
                st.success("所有数据已成功清空！")
                # 清空会话状态
                st.session_state.all_leaders = get_all_leaders()
                if 'selected_name' in st.session_state:
                    del st.session_state.selected_name
            else:
                st.error("数据清空失败，请重试。")
        
        # 数据库备份
        if st.button("备份数据库", key="backup_db_button"):
            backup_database()
    
    def get_all_leaders_assessments():
        """获取所有网格长的最新评估数据"""
        conn = get_db_connection()
        if conn is None:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, g.name, g.area 
                FROM assessments a
                JOIN grid_leaders g ON a.leader_id = g.id
                WHERE (a.leader_id, a.date) IN (
                    SELECT leader_id, MAX(date) 
                    FROM assessments 
                    GROUP BY leader_id
                )
            """)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            st.error(f"获取所有网格长评估数据失败: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    # 主界面内容
    if 'selected_name' in st.session_state and st.session_state.selected_name:
        selected_leader = next((leader for leader in all_leaders if leader["name"] == st.session_state.selected_name), None)
        if selected_leader:
            leader_id = selected_leader["id"]
            assessments = get_leader_assessments(leader_id)
    
            if assessments:
                # 找到对应日期的评估记录，若无则使用最新记录
                selected_assessment = next(
                    (a for a in assessments if a["date"] == selected_date),
                    assessments[0]
                )
    
                st.subheader(f"网格长: {selected_leader['name']} - {selected_leader['area']}")
                st.subheader(f"评估日期: {selected_assessment['date']}")
    
                # 显示评估分数
                st.subheader("能力评估分数")
                col1, col2 = st.columns(2)
                for i, dim in enumerate(DIMENSIONS):
                    col = col1 if i < len(DIMENSIONS)/2 else col2
                    with col:
                        score = selected_assessment.get(dim_to_db_col[dim], 0)
                        st.metric(dim, f"{score:.2f}分")
    
                # 计算综合得分
                scores = {dim: selected_assessment.get(dim_to_db_col[dim], 0) for dim in DIMENSIONS}
                total_score = calculate_total_score(scores, WEIGHTS, DIMENSIONS)
    
                st.subheader(f"综合得分: {total_score:.2f}分")
    
                # 显示评估等级
                grade = "优秀" if total_score >= THRESHOLDS["优秀"] else \
                        "良好" if total_score >= THRESHOLDS["良好"] else \
                        "合格" if total_score >= THRESHOLDS["合格"] else "待改进"
                st.subheader(f"评估等级: {grade}")
    
                # 显示全量网格分值排名对比
                all_assessments = get_all_leaders_assessments()
                all_scores = []
                for assessment in all_assessments:
                    scores = {dim: assessment.get(dim_to_db_col[dim], 0) for dim in DIMENSIONS}
                    total_score = calculate_total_score(scores, WEIGHTS, DIMENSIONS)
                    all_scores.append({
                        "姓名": assessment['name'],
                        "辖区": assessment['area'],
                        "综合得分": total_score,
                        "评估等级": "优秀" if total_score >= THRESHOLDS["优秀"] else
                                  "良好" if total_score >= THRESHOLDS["良好"] else
                                  "合格" if total_score >= THRESHOLDS["合格"] else "待改进"
                    })
    
                # 按综合得分排序
                all_scores.sort(key=lambda x: x["综合得分"], reverse=True)
                # 添加排名列
                for i, score_info in enumerate(all_scores, start=1):
                    score_info["排名"] = i
    
                st.subheader("全量网格分值排名对比")
                df = pd.DataFrame(all_scores)
                # 高亮显示选中的网格长
                def highlight_selected(s):
                    if s["姓名"] == selected_leader["name"]:
                        return ['background-color: yellow'] * len(s)
                    return [''] * len(s)
                st.dataframe(df.style.apply(highlight_selected, axis=1))
    
                # 显示网格具体得分结果
                st.subheader("网格具体得分结果")
                st.write(pd.DataFrame({
                    "维度": DIMENSIONS,
                    "得分": [selected_assessment.get(dim_to_db_col[dim], 0) for dim in DIMENSIONS]
                }))
            else:
                st.warning("该网格长暂无评估数据。")
        else:
            st.warning("未找到选中的网格长数据。")
    else:
        st.info("请在侧边栏选择网格长。")