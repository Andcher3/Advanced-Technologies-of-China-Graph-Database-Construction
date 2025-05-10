import streamlit as st
import time
import json
import requests
import sqlite3
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="中国先进知识问答系统", layout="wide", initial_sidebar_state="expanded")

# --- 后端API配置 ---
BACKEND_API_URL = "http://10.15.80.180:8000/answer" # 您的后端API地址

# --- 数据库配置 ---
DB_NAME = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 创建 chats 表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        chat_id TEXT PRIMARY KEY,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # 创建 messages 表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
    )
    """)
    conn.commit()
    conn.close()

# --- 数据库操作函数 ---
def create_new_chat_entry(chat_id, title="新对话"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?)", (chat_id, title))
        conn.commit()
    except sqlite3.IntegrityError: # chat_id 可能已存在 (理论上基于时间戳的ID不会)
        st.error(f"创建对话条目失败，ID {chat_id} 可能已存在。")
    finally:
        conn.close()

def add_message_to_db(chat_id, role, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now()
    try:
        cursor.execute("INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                       (chat_id, role, content, now))
        # 更新 chat 的 last_updated_at
        cursor.execute("UPDATE chats SET last_updated_at = ? WHERE chat_id = ?", (now, chat_id))
        conn.commit()
    except Exception as e:
        st.error(f"保存消息到数据库失败: {e}")
    finally:
        conn.close()

def get_chat_messages_from_db(chat_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (chat_id,))
    messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    return messages

def get_all_chats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 按最后更新时间降序排列，最新的对话在最前面
    cursor.execute("SELECT chat_id, title, last_updated_at FROM chats ORDER BY last_updated_at DESC")
    chats = [{"chat_id": row[0], "title": row[1] or f"对话 - {row[0]}", "last_updated_at": row[2]} for row in cursor.fetchall()]
    conn.close()
    return chats

def update_chat_title_in_db(chat_id, title):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))
        conn.commit()
    except Exception as e:
        st.error(f"更新对话标题失败: {e}")
    finally:
        conn.close()

# 初始化数据库
init_db()


# --- 初始化 session_state ---
# 'messages' 和 'current_chat_id' 将在选择或创建新对话时设置
if "neo4j_enabled" not in st.session_state:
    st.session_state.neo4j_enabled = False
if "chat_loaded" not in st.session_state: # 用于标记是否已加载或创建了一个对话
    st.session_state.chat_loaded = False


# --- 后端API调用函数 (已更新) ---
def call_backend_api(user_input: str, history: list, use_neo4j: bool, chat_id: str):
    st.toast(f"正在调用后端 (Neo4j: {'启用' if use_neo4j else '禁用'})...")
    payload = {
        "query": user_input,
        "history": history,
        "neo4j_enabled": use_neo4j,
        "session_id": chat_id
    }
    # print(f"发送给后端的负载: {json.dumps(payload, ensure_ascii=False)}") # 用于 streamlit run app.py > streamlit.log 2>&1 查看

    try:
        response = requests.post(BACKEND_API_URL, json=payload, timeout=120) # 增加超时
        # print(f"后端状态码: {response.status_code}")
        # print(f"后端响应内容: {response.text}")
        response.raise_for_status()
        backend_response = response.json() # 假设后端总是返回JSON
        assistant_reply = backend_response.get("answer", "抱歉，后端没有返回有效的回答。")
    except requests.exceptions.Timeout:
        st.error("调用后端API超时，请稍后再试或检查后端服务。")
        assistant_reply = "抱歉，请求超时。"
    except requests.exceptions.ConnectionError:
        st.error(f"无法连接到后端服务 {BACKEND_API_URL}，请检查后端是否正在运行以及网络连接。")
        assistant_reply = "抱歉，无法连接到服务。"
    except requests.exceptions.HTTPError as e:
        st.error(f"后端API返回错误: {e.response.status_code} - {e.response.text}")
        assistant_reply = f"抱歉，后端服务出错 ({e.response.status_code})。"
    except json.JSONDecodeError:
        st.error(f"后端返回了无效的JSON格式。响应内容: {response.text if 'response' in locals() else 'N/A'}")
        assistant_reply = "抱歉，后端响应格式错误。"
    except Exception as e: # 捕获其他未知错误
        st.error(f"调用后端时发生未知错误: {e}")
        assistant_reply = "抱歉，发生未知错误。"
    return assistant_reply

# --- UI 渲染逻辑 ---

# 侧边栏
with st.sidebar:
    st.image("https://streamlit.io/images/brand/streamlit-logo-secondary-colormark-darktext.svg", width=150)
    st.title("问答系统控制面板")
    st.markdown("---")

    if st.button("🚀 新建对话", use_container_width=True, type="primary"):
        st.session_state.current_chat_id = f"chat_{int(time.time())}"
        title = f"新对话 @ {datetime.now().strftime('%H:%M:%S')}"
        create_new_chat_entry(st.session_state.current_chat_id, title)
        st.session_state.messages = [{"role": "assistant", "content": "您好！我是中国先进知识问答助手，新对话已开始。"}]
        add_message_to_db(st.session_state.current_chat_id, "assistant", st.session_state.messages[0]["content"])
        st.session_state.chat_loaded = True
        st.toast("新的对话已创建！")
        st.rerun()

    st.markdown("---")
    st.subheader("历史对话")
    all_chats = get_all_chats()
    if not all_chats and not st.session_state.chat_loaded: # 如果没有历史对话，且没有加载任何对话
        st.caption("暂无历史对话。点击“新建对话”开始。")
    
    for chat in all_chats:
        # 为每个历史对话创建一个按钮，点击后加载该对话
        if st.button(f"{chat['title']} ({datetime.strptime(chat['last_updated_at'][:19], '%Y-%m-%d %H:%M:%S').strftime('%y/%m/%d %H:%M')})", 
                     key=f"load_{chat['chat_id']}", use_container_width=True):
            st.session_state.current_chat_id = chat['chat_id']
            st.session_state.messages = get_chat_messages_from_db(chat['chat_id'])
            st.session_state.chat_loaded = True
            st.toast(f"已加载对话: {chat['title']}")
            st.rerun()
    
    st.markdown("---")
    st.session_state.neo4j_enabled = st.toggle(
        "启用 Neo4j 知识增强",
        value=st.session_state.get("neo4j_enabled", False), # 保证在session_state中存在
        help="启用后，系统将尝试使用知识图谱来增强回答的准确性和深度。"
    )
    if st.session_state.neo4j_enabled:
        st.info("Neo4j 知识增强已启用。")
    else:
        st.warning("Neo4j 知识增强已禁用。")

    st.markdown("---")
    st.markdown("### 关于系统")
    st.caption("本系统旨在提供关于中国先进技术领域的知识问答服务。")
    if st.session_state.get("current_chat_id"):
        st.caption(f"当前对话ID: {st.session_state.current_chat_id[-6:]}") # 显示部分ID


# 主聊天界面
st.header("🇨🇳 中国先进知识问答系统")

if not st.session_state.chat_loaded:
    st.info("请从侧边栏选择一个历史对话加载，或点击“新建对话”开始。")
else:
    st.caption(f"当前对话: {next((c['title'] for c in all_chats if c['chat_id'] == st.session_state.current_chat_id), '新对话')}")
    # 显示历史消息
    if "messages" in st.session_state:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    else:
        st.session_state.messages = [] # 确保 messages 存在

    # 获取用户输入
    if prompt := st.chat_input("请输入您的问题..."):
        # 1. 将用户消息添加到会话状态、数据库并显示
        st.session_state.messages.append({"role": "user", "content": prompt})
        add_message_to_db(st.session_state.current_chat_id, "user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        # 如果是这个对话的第一条用户消息，并且标题还是默认的，尝试更新标题
        if len([m for m in st.session_state.messages if m['role'] == 'user']) == 1:
            current_chat_info = next((c for c in all_chats if c['chat_id'] == st.session_state.current_chat_id), None)
            if current_chat_info and current_chat_info['title'].startswith("新对话 @"):
                new_title = prompt[:30] + "..." if len(prompt) > 30 else prompt
                update_chat_title_in_db(st.session_state.current_chat_id, new_title)
                # st.rerun() # 可以选择 rerun 来立即更新侧边栏标题，但会打断流程，或者下次加载时更新

        # 2. 调用后端API获取助手回复
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("思考中...")

            history_for_backend = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in st.session_state.messages[:-1] # 发送直到上一条消息（即当前用户输入之前的所有消息）
            ]

            assistant_response = call_backend_api(
                user_input=prompt,
                history=history_for_backend,
                use_neo4j=st.session_state.neo4j_enabled,
                chat_id=st.session_state.current_chat_id
            )
            message_placeholder.markdown(assistant_response)

        # 3. 将助手回复添加到会话状态和数据库
        st.session_state.messages.append({"role": "assistant", "content": assistant_response})
        add_message_to_db(st.session_state.current_chat_id, "assistant", assistant_response)
        # st.rerun() # 如果希望每次回复后都刷新整个界面（包括侧边栏的更新时间），可以取消注释，但会使输入框失焦

# 调试信息 (可选)
st.sidebar.markdown("---")
st.sidebar.subheader("💡 调试信息")
if st.sidebar.checkbox("显示 Session State"):
    st.sidebar.json(st.session_state.to_dict(), expanded=False)