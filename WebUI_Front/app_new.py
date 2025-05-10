import streamlit as st
import time
import json
import requests
import sqlite3
from datetime import datetime
import uuid

# --- 页面配置 ---
st.set_page_config(page_title="中国先进知识问答系统", layout="wide", initial_sidebar_state="expanded")

# --- 后端API配置 ---
BACKEND_API_URL = "http://10.15.80.180:8000/answer" # 您的后端API地址

# --- 数据库配置 ---
DB_NAME = "HaMmer_chat_history.db"

# --- 数据库初始化和操作函数 (与您之前版本基本一致，确保 ON DELETE CASCADE 和 check_same_thread=False) ---
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        chat_id TEXT PRIMARY KEY,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (chat_id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()

def create_new_chat_entry(chat_id, title="新对话"):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?)", (chat_id, title))
        conn.commit()
    except sqlite3.IntegrityError:
        st.error(f"创建对话条目失败，ID {chat_id} 可能已存在。")
    finally:
        conn.close()

def add_message_to_db(chat_id, role, content):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    now = datetime.now()
    message_uuid = str(uuid.uuid4())
    try:
        cursor.execute("INSERT INTO messages (message_id, chat_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                       (message_uuid, chat_id, role, content, now))
        cursor.execute("UPDATE chats SET last_updated_at = ? WHERE chat_id = ?", (now, chat_id))
        conn.commit()
    except Exception as e:
        st.error(f"保存消息到数据库失败: {e}")
    finally:
        conn.close()

def get_chat_messages_from_db(chat_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (chat_id,))
    messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    return messages

def get_all_chats():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title, last_updated_at FROM chats ORDER BY last_updated_at DESC")
    chats = [{"chat_id": row[0], "title": row[1] or f"对话 - {row[0]}", "last_updated_at": row[2]} for row in cursor.fetchall()]
    conn.close()
    return chats

def update_chat_title_in_db(chat_id, title):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))
        conn.commit()
    except Exception as e:
        st.error(f"更新对话标题失败: {e}")
    finally:
        conn.close()

def delete_chat_from_db(chat_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        conn.commit()
        st.toast(f"对话已删除。")
    except Exception as e:
        st.error(f"删除对话失败: {e}")
    finally:
        conn.close()

init_db()

# --- 初始化 session_state ---
if "neo4j_enabled" not in st.session_state:
    st.session_state.neo4j_enabled = False
if "chat_loaded" not in st.session_state:
    st.session_state.chat_loaded = False
if "processing_response" not in st.session_state:
    st.session_state.processing_response = False
if "request_cancelled" not in st.session_state:
    st.session_state.request_cancelled = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

# --- 后端API调用函数 (保持不变，但注意检查 request_cancelled) ---
def call_backend_api(user_input: str, history: list, use_neo4j: bool, chat_id: str):
    # (您的 call_backend_api 函数代码，确保它在开始和等待时检查 st.session_state.request_cancelled)
    if st.session_state.get("request_cancelled", False):
        st.session_state.request_cancelled = False # 重置
        return "操作已由用户终止。"

    st.toast(f"正在调用后端 (Neo4j: {'启用' if use_neo4j else '禁用'})...")
    payload = {
        "query": user_input,
        "history": history,
        "neo4j_enabled": use_neo4j,
        "session_id": chat_id
    }
    try:
        print(f"API请求: {BACKEND_API_URL} - {payload}")  # 调试信息
        response = requests.post(BACKEND_API_URL, json=payload, timeout=120)
        print(f"API响应: {response.status_code} - {response.text}")  # 调试信息
        if st.session_state.get("request_cancelled", False):
            st.session_state.request_cancelled = False
            return "操作已由用户终止 (API调用期间)。"
        response.raise_for_status()
        backend_response = response.json()
        assistant_reply = backend_response.get("answer", "抱歉，后端没有返回有效的回答。")
    except requests.exceptions.Timeout:
        if st.session_state.get("request_cancelled", False):
            st.session_state.request_cancelled = False
            return "操作已由用户终止 (超时期间)。"
        st.error("调用后端API超时，请稍后再试或检查后端服务。")
        assistant_reply = "抱歉，请求超时。"
    except requests.exceptions.ConnectionError:
        st.error(f"无法连接到后端服务 {BACKEND_API_URL}。")
        assistant_reply = "抱歉，无法连接到服务。"
    except requests.exceptions.HTTPError as e:
        st.error(f"后端API返回错误: {e.response.status_code} - {e.response.text}")
        assistant_reply = f"抱歉，后端服务出错 ({e.response.status_code})。"
    except json.JSONDecodeError:
        st.error(f"后端返回了无效的JSON格式。")
        assistant_reply = "抱歉，后端响应格式错误。"
    except Exception as e:
        st.error(f"调用后端时发生未知错误: {e}")
        assistant_reply = "抱歉，发生未知错误。"
    return assistant_reply


# --- UI 渲染逻辑 ---

# 侧边栏
with st.sidebar:
    st.image("./WebUI_Front/assets/logo.png", width=150)
    st.title("问答系统控制面板")
    st.markdown("---")

    if st.button("🚀 新建对话", use_container_width=True, type="primary"):
        new_chat_id = f"chat_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        st.session_state.current_chat_id = new_chat_id
        title = f"新对话 @ {datetime.now().strftime('%H:%M:%S')}"
        create_new_chat_entry(st.session_state.current_chat_id, title)
        welcome_message = "您好！我是中国先进知识问答助手，新对话已开始。"
        st.session_state.messages = [{"role": "assistant", "content": welcome_message}]
        add_message_to_db(st.session_state.current_chat_id, "assistant", welcome_message)
        st.session_state.chat_loaded = True
        st.session_state.processing_response = False
        st.session_state.request_cancelled = False
        st.toast("新的对话已创建！")
        st.rerun()

    st.markdown("---")
    st.subheader("历史对话")
    all_chats = get_all_chats() # 获取一次，供后续使用

    if not all_chats and not st.session_state.chat_loaded:
        st.caption("暂无历史对话。")

    for chat_idx, chat in enumerate(all_chats): # 使用 enumerate 获取索引以创建唯一 key
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            if st.button(f"{chat['title']} ({datetime.strptime(chat['last_updated_at'][:19], '%Y-%m-%d %H:%M:%S').strftime('%y/%m/%d %H:%M')})",
                         key=f"load_{chat['chat_id']}_{chat_idx}", # 确保 key 的唯一性
                         use_container_width=True,
                         type="secondary" if st.session_state.current_chat_id != chat['chat_id'] else "primary"):
                st.session_state.current_chat_id = chat['chat_id']
                st.session_state.messages = get_chat_messages_from_db(chat['chat_id'])
                st.session_state.chat_loaded = True
                st.session_state.processing_response = False
                st.session_state.request_cancelled = False
                st.toast(f"已加载对话: {chat['title']}")
                st.rerun()
        with col2:
            delete_key = f"delete_{chat['chat_id']}_{chat_idx}"
            confirm_key = f"confirm_delete_{chat['chat_id']}_{chat_idx}"
            cancel_key = f"cancel_delete_{chat['chat_id']}_{chat_idx}"

            if st.session_state.get(confirm_key):
                if st.button("🗑️", key=delete_key, help="确认删除", use_container_width=True, type="primary"): # 突出确认删除
                    delete_chat_from_db(chat['chat_id'])
                    if st.session_state.current_chat_id == chat['chat_id']:
                        st.session_state.chat_loaded = False
                        st.session_state.current_chat_id = None
                        st.session_state.messages = []
                    del st.session_state[confirm_key]
                    st.rerun()
                if st.button("❌", key=cancel_key, help="取消删除", use_container_width=True):
                    del st.session_state[confirm_key]
                    st.rerun()
            else:
                if st.button("🗑️", key=delete_key, help="删除此对话", use_container_width=True):
                    st.session_state[confirm_key] = True
                    st.rerun() # 重新运行以显示确认/取消按钮

    st.markdown("---")
    st.session_state.neo4j_enabled = st.toggle(
        "启用 Neo4j 知识增强",
        value=st.session_state.get("neo4j_enabled", False),
        help="启用后，系统将尝试使用知识图谱来增强回答的准确性和深度。"
    )
    # (Neo4j 状态显示信息)
    if st.session_state.neo4j_enabled:
        st.info("Neo4j 知识增强已启用。")
    else:
        st.warning("Neo4j 知识增强已禁用。")

    st.markdown("---")
    # (关于系统和对话ID显示)
    st.markdown("### 关于系统")
    st.caption("本系统旨在提供关于中国先进技术领域的知识问答服务。")
    if st.session_state.get("current_chat_id"):
        st.caption(f"当前对话ID: ...{st.session_state.current_chat_id[-6:]}")

# --- 主聊天界面 ---
st.header("🇨🇳 中国先进知识问答系统")

if not st.session_state.chat_loaded:
    st.info("请从侧边栏选择一个历史对话加载，或点击“新建对话”开始。")
else:
    current_chat_title = "新对话" # 默认值
    if st.session_state.current_chat_id and all_chats: # 确保 all_chats 已获取
         chat_info = next((c for c in all_chats if c['chat_id'] == st.session_state.current_chat_id), None)
         if chat_info:
             current_chat_title = chat_info['title']
    st.caption(f"当前对话: {current_chat_title}")

    # 1. 始终先渲染所有已存在的消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 2. 如果正在处理响应，显示终止按钮，并可能显示 "思考中..." (由API调用块处理)
    stop_button_placeholder = st.empty() # 为终止按钮创建占位符
    if st.session_state.processing_response and not st.session_state.request_cancelled:
        # 只有在 processing_response 为 True 且请求未被取消时才显示终止按钮
        if stop_button_placeholder.button("🚫 终止回答", key="cancel_response_button"): # 移除 type 参数
            st.session_state.request_cancelled = True
            st.toast("正在尝试终止回答...")
            # 注意：点击此按钮后，下面的API调用块中的 call_backend_api 会检查 request_cancelled
            # 并提前返回。然后 processing_response 会被设为 False，再次 rerun 后此按钮消失。
            # 为了让按钮的响应更即时，可以考虑在这里直接 rerun，
            # 但要确保 call_backend_api 优雅处理。目前不加 rerun，让流程自然结束。

    # 3. 获取用户输入
    user_prompt = st.chat_input(
        "请输入您的问题...",
        disabled=st.session_state.processing_response,
        key="chat_input_main"
    )

    # 4. 处理用户的新输入
    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        add_message_to_db(st.session_state.current_chat_id, "user", user_prompt)
        
        st.session_state.processing_response = True # 进入处理状态
        st.session_state.request_cancelled = False  # 重置取消标志
        st.rerun() # 立即重绘，显示用户消息，禁用输入框，显示终止按钮

    # 5. 如果当前处于处理状态 (由上一轮的 user_prompt 触发的 rerun 之后)
    if st.session_state.processing_response and not user_prompt: # `not user_prompt`确保这是rerun后的执行轮次
        
        # 从 st.session_state.messages 获取最新的用户提问
        latest_user_message_content = ""
        if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
            latest_user_message_content = st.session_state.messages[-1]["content"]
        
        if latest_user_message_content: # 确保我们有内容可发送
            # 更新对话标题 (如果需要)
            if len([m for m in st.session_state.messages if m['role'] == 'user']) == 1:
                current_chat_info = next((c for c in all_chats if c['chat_id'] == st.session_state.current_chat_id), None)
                if current_chat_info and current_chat_info['title'].startswith("新对话 @"):
                    new_title = latest_user_message_content[:30] + "..." if len(latest_user_message_content) > 30 else latest_user_message_content
                    update_chat_title_in_db(st.session_state.current_chat_id, new_title)
                    # 为了立即更新侧边栏标题，可能需要再次 rerun，但会增加复杂性。
                    # 或者接受标题在下次加载/刷新时更新。

            # 显示 "思考中..." 并调用 API
            with st.chat_message("assistant"): # 这个上下文会用于显示 "思考中" 和最终的助手回复
                message_placeholder = st.empty()
                if not st.session_state.request_cancelled: # 仅在未取消时显示 "思考中"
                    message_placeholder.markdown("思考中...")

                history_for_backend = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in st.session_state.messages[:-1] # 发送直到上一条用户消息
                ]
                
                assistant_response = call_backend_api(
                    user_input=latest_user_message_content,
                    history=history_for_backend,
                    use_neo4j=st.session_state.neo4j_enabled,
                    chat_id=st.session_state.current_chat_id
                )

                message_placeholder.markdown(assistant_response) # 显示最终回复或 "已终止" 消息
            
            # 只有在未被用户取消的情况下，才将有效回复加入历史
            if not (st.session_state.request_cancelled and assistant_response == "操作已由用户终止。" or assistant_response == "操作已由用户终止 (API调用期间)。" or assistant_response == "操作已由用户终止 (超时期间)。"):
                 if assistant_response not in ["抱歉，请求超时。", "抱歉，无法连接到服务。", "抱歉，后端响应格式错误。", "抱歉，发生未知错误."] and not assistant_response.startswith("抱歉，后端服务出错"): # 避免保存纯错误信息
                    st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                    add_message_to_db(st.session_state.current_chat_id, "assistant", assistant_response)

        # 无论API调用结果如何（成功、失败、取消），处理流程结束
        st.session_state.processing_response = False
        st.session_state.request_cancelled = False # 重置取消状态
        stop_button_placeholder.empty() # 清除终止按钮（如果它还在）
        st.rerun() # 刷新UI：启用输入框，移除终止按钮，显示最新消息列表

# 调试信息 (可选)
st.sidebar.markdown("---")
st.sidebar.subheader("💡 调试信息")
if st.sidebar.checkbox("显示 Session State"):
    st.sidebar.json(st.session_state.to_dict(), expanded=False)