import streamlit_authenticator as stauth

# 假设 password 是一个字符串
password = "admin"
# 直接传入包含字符串的列表
hashed_password = stauth.Hasher([password]).generate()

print(hashed_password)