import streamlit as st
import requests  # 用于未来与后端API通信
import uuid  # 用于生成唯一的聊天会话ID
from datetime import datetime

# --- 页面基础配置 ---
st.set_page_config(
    page_title="中国先进知识问答系统",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 全局样式与资源 (CDN) ---
st.markdown(
    """
    <head>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    </head>
    <style>
        /* --- 美化滚动条 --- */
        ::-webkit-scrollbar {
            width: 10px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        ::-webkit-scrollbar-thumb {
            background: #888;
            border_radius: 10px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #555;
        }

        /* --- 聊天气泡样式 --- */
        .chat-bubble {
            padding: 10px 15px;
            border-radius: 20px;
            margin-bottom: 10px;
            max-width: 80%;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .user-bubble {
            background-color: #DCF8C6;
            align-self: flex-end;
            margin-left: auto;
            border-bottom-right-radius: 5px;
        }
        .assistant-bubble {
            background-color: #FFFFFF;
            align-self: flex-start;
            margin-right: auto;
            border-bottom-left-radius: 5px;
            border: 1px solid #e0e0e0;
        }
        .chat-icon {
            margin-right: 8px;
            font-size: 1.2em;
        }
        .stButton>button {
            border-radius: 20px;
            border: 1px solid #007bff;
            color: #007bff;
        }
        .stButton>button:hover {
            border: 1px solid #0056b3;
            color: #0056b3;
            background-color: #e9ecef;
        }
        .sidebar .stButton>button {
            width: 100%;
            margin-bottom: 5px;
            border-radius: 8px;
            justify-content: flex-start;
            padding: 8px 12px;
        }
        .sidebar .stButton>button:hover {
            background-color: #f0f2f6;
        }
        .chat-input textarea {
            border-radius: 18px !important;
            border: 1px solid #ced4da !important;
            padding: 10px 15px !important;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
            height: calc(100vh - 220px); /* 稍微调整高度以适应可能的header变化 */
            overflow-y: auto;
            padding: 10px;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            background-color: #f9f9f9;
        }
    </style>
""",
    unsafe_allow_html=True,
)


# --- 初始化 Session State ---
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = {}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "neo4j_enabled" not in st.session_state:
    st.session_state.neo4j_enabled = True

BACKEND_API_URL = "http://127.0.0.1:8000/qasystem/chat"


# --- 辅助函数 ---
def create_new_chat():
    chat_id = str(uuid.uuid4())
    now = datetime.now()
    chat_name = f"对话 {now.strftime('%Y-%m-%d %H:%M:%S')}"
    st.session_state.chat_sessions[chat_id] = {"name": chat_name, "messages": []}
    st.session_state.current_chat_id = chat_id
    st.success(f"已创建新对话: {chat_name}")
    st.rerun()  # 已修复


def switch_chat_session(session_id):
    if session_id in st.session_state.chat_sessions:
        st.session_state.current_chat_id = session_id
        st.rerun()  # 已修复
    else:
        st.error("无法找到该对话。")


def get_current_chat_messages():
    if (
        st.session_state.current_chat_id
        and st.session_state.current_chat_id in st.session_state.chat_sessions
    ):
        return st.session_state.chat_sessions[st.session_state.current_chat_id][
            "messages"
        ]
    return []


def add_message_to_current_chat(role, content):
    if (
        st.session_state.current_chat_id
        and st.session_state.current_chat_id in st.session_state.chat_sessions
    ):
        st.session_state.chat_sessions[st.session_state.current_chat_id][
            "messages"
        ].append({"role": role, "content": content})


def get_chat_history_for_api(session_id):
    if session_id and session_id in st.session_state.chat_sessions:
        return st.session_state.chat_sessions[session_id]["messages"]
    return []


# --- 侧边栏 (Sidebar) ---
with st.sidebar:
    # 使用 st.markdown 来创建带图标的标题
    st.markdown("## <i class='fas fa-bars'></i> 导航与设置", unsafe_allow_html=True)
    st.divider()

    if st.button("➕ 新建对话", key="new_chat_button", help="开始一个新的聊天会话"):
        create_new_chat()
    st.divider()

    st.markdown("#### <i class='fas fa-history'></i> 对话历史", unsafe_allow_html=True)
    if not st.session_state.chat_sessions:
        st.caption("还没有对话记录。")
    else:
        sorted_sessions = sorted(
            st.session_state.chat_sessions.items(),
            key=lambda item: item[1].get("name", item[0]),
            reverse=True,
        )
        for session_id, session_data in sorted_sessions:
            session_name = session_data.get("name", f"对话 {session_id[:8]}")
            col1, col2 = st.columns([0.85, 0.15])
            with col1:
                if st.button(
                    f"{'➡️ ' if st.session_state.current_chat_id == session_id else ''}{session_name}",
                    key=f"switch_chat_{session_id}",
                    help=f"切换到: {session_name}",
                ):
                    switch_chat_session(session_id)
                # with col2:
                if st.button(
                    "🗑️",
                    key=f"delete_chat_{session_id}",
                    help=f"删除对话: {session_name}",
                ):
                    if st.session_state.current_chat_id == session_id:
                        st.session_state.current_chat_id = None
                    del st.session_state.chat_sessions[session_id]
                    st.rerun()  # 已修复

    st.divider()
    st.markdown("#### <i class='fas fa-cogs'></i> 系统设置", unsafe_allow_html=True)
    # st.toggle 的 label 参数不支持直接的 HTML，但我们可以用 st.markdown 来实现带图标的标签效果
    st.markdown(
        "##### <i class='fas fa-database'></i> **启用 Neo4j 知识增强**",
        unsafe_allow_html=True,
    )
    st.session_state.neo4j_enabled = st.toggle(
        label=" ",  # 将标签留空，因为我们已经在上面用markdown创建了
        value=st.session_state.neo4j_enabled,
        help="开启后，系统将尝试利用 Neo4j 图数据库中的知识来增强回答的准确性和深度。",
        label_visibility="collapsed",  # 隐藏toggle自带的label
    )

    if st.session_state.neo4j_enabled:
        st.caption("Neo4j 增强已启用。")
    else:
        st.caption("Neo4j 增强已禁用。")

    st.divider()
    st.markdown("---")
    st.caption("中国先进知识问答系统 v0.1")


# --- 主聊天界面 ---
if not st.session_state.current_chat_id and st.session_state.chat_sessions:
    latest_session_id = list(st.session_state.chat_sessions.keys())[-1]
    switch_chat_session(latest_session_id)
elif not st.session_state.chat_sessions:
    create_new_chat()


if st.session_state.current_chat_id:
    current_chat_name = st.session_state.chat_sessions[
        st.session_state.current_chat_id
    ].get("name", "当前对话")
    # 使用 st.markdown 替换 st.header 来支持 HTML 图标
    st.markdown(
        f"<h3><i class='fas fa-comments'></i> {current_chat_name}</h3>",
        unsafe_allow_html=True,
    )

    chat_display_container = st.container()
    with chat_display_container:
        st.markdown(
            "<div class='chat-container' id='chat-container-div'>",
            unsafe_allow_html=True,
        )
        messages = get_current_chat_messages()
        if not messages:
            # 使用 st.markdown 来确保图标能正确显示
            st.markdown(
                """
                <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                     <div class="chat-bubble assistant-bubble">
                        <i class="fas fa-robot chat-icon" style="color: #007bff;"></i>
                        您好！我是中国先进知识问答助手，请问有什么可以帮助您的？
                    </div>
                </div>
            """,
                unsafe_allow_html=True,
            )

        for msg in messages:
            role = msg["role"]
            content = msg["content"]  # 假设content已经是HTML安全的，或者后端会处理
            if role == "user":
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                        <div class="chat-bubble user-bubble">
                            <i class="fas fa-user chat-icon" style="color: #4CAF50;"></i>
                            {content}
                        </div>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
            elif role == "assistant":
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                         <div class="chat-bubble assistant-bubble">
                            <i class="fas fa-robot chat-icon" style="color: #007bff;"></i>
                            {content}
                        </div>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)

    user_query = st.chat_input(
        "请输入您的问题...", key=f"chat_input_{st.session_state.current_chat_id}"
    )

    if user_query:
        # 清理用户输入，防止XSS（如果直接显示用户输入且未处理）
        # Streamlit的st.markdown默认会对非unsafe_allow_html的内容进行一定的清理
        # 但如果用户输入的内容本身就包含恶意HTML，且你打算在某处用unsafe_allow_html显示它，则需要小心
        # 此处我们假设后端会处理或内容本身是纯文本
        cleaned_user_query = user_query  # 简单示例，实际可能需要更复杂的清理库如bleach
        add_message_to_current_chat("user", cleaned_user_query)
        st.rerun()  # 已修复

        with st.spinner("思考中，请稍候..."):  # spinner的文本不支持HTML，所以移除了图标
            try:
                history_for_api = get_chat_history_for_api(
                    st.session_state.current_chat_id
                )
                api_payload = {
                    "query": cleaned_user_query,
                    "history": history_for_api[:-1],
                    "neo4j_enabled": st.session_state.neo4j_enabled,
                    "session_id": st.session_state.current_chat_id,
                }
                # st.write(f"调试信息：发送到后端的数据：{api_payload}")

                # 【模拟后端响应】
                import time

                time.sleep(1.5)
                assistant_reply_content = f"收到您的问题：“{cleaned_user_query}”。"
                if st.session_state.neo4j_enabled:
                    assistant_reply_content += "<br><br><i class='fas fa-database'></i> (Neo4j 知识增强已启用...)"
                    if "人工智能" in cleaned_user_query:
                        assistant_reply_content += "<br><br><i class='fas fa-project-diagram'></i> <b>Neo4j发现：</b> “人工智能” 关联到 “深度学习”..."
                else:
                    assistant_reply_content += "<br><br>(Neo4j 知识增强未启用)"
                # (模拟结束)

                add_message_to_current_chat("assistant", assistant_reply_content)

            except requests.exceptions.RequestException as e:
                st.error(f"请求后端API失败: {e}")
                add_message_to_current_chat(
                    "assistant", "抱歉，连接问答服务时出现问题，请稍后再试。"
                )
            except Exception as e:
                st.error(f"处理时发生未知错误: {e}")
                add_message_to_current_chat("assistant", "抱歉，系统内部出现未知错误。")

        st.rerun()  # 已修复

else:
    st.info("请在左侧选择一个对话或新建一个对话开始。")
    if st.button("🚀 开始一个新对话"):
        create_new_chat()
