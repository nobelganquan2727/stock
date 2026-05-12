import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
USER_OPEN_ID = os.getenv("FEISHU_USER_OPEN_ID")

def get_token():
    if not APP_ID or not APP_SECRET:
        print("未配置飞书 APP_ID 或 APP_SECRET")
        return None
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return resp.json().get("tenant_access_token")

def send_message(text: str):
    token = get_token()
    if not token:
        return
    if not USER_OPEN_ID:
        print("未配置飞书 USER_OPEN_ID")
        return
        
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 使用 json.dumps 处理 content，避免手动拼接引号引发错误
    payload = {
        "receive_id": USER_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False)
    }
    resp = requests.post(url, headers=headers, json=payload)
    print("Feishu Push Response:", resp.json())


def send_image(image_path: str):
    token = get_token()
    if not token:
        return
    if not USER_OPEN_ID:
        print("未配置飞书 USER_OPEN_ID")
        return

    upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    with open(image_path, "rb") as image:
        resp = requests.post(
            upload_url,
            headers=headers,
            data={"image_type": "message"},
            files={"image": image},
        )
    upload_result = resp.json()
    print("Feishu Image Upload Response:", upload_result)

    image_key = upload_result.get("data", {}).get("image_key")
    if not image_key:
        return

    send_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    send_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": USER_OPEN_ID,
        "msg_type": "image",
        "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
    }
    send_resp = requests.post(send_url, headers=send_headers, json=payload)
    print("Feishu Image Push Response:", send_resp.json())
