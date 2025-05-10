import streamlit as st
import time
import json # 用于处理发送给后端的历史记录
import requests # 真实场景下调用后端API

# --- 页面配置 ---
st.set_page_config(page_title="中国先进知识问答系统", layout="wide", initial_sidebar_state="expanded")

# --- 后端API配置 (占位) ---
BACKEND_API_URL = "http://10.15.80.180:8000/answer" # 假设的后端API地址

# --- 初始化 session_state ---
if "messages" not in st.session_state:
    st.session_state.messages = [] # 存储对话消息
if "neo4j_enabled" not in st.session_state:
    st.session_state.neo4j_enabled = False # 默认不启用 Neo4j 增强
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = f"chat_{int(time.time())}" # 简单地用时间戳作为对话ID

# --- 模拟后端调用函数 ---
def call_backend_api(user_input: str, history: list, use_neo4j: bool, chat_id: str):
    """
    模拟调用后端API。
    真实场景下，这里会使用 requests.post 发送请求。
    """
    st.toast(f"正在调用后端 (Neo4j: {'启用' if use_neo4j else '禁用'})...")
    
    # 准备发送给后端的数据结构
    payload = {
        "query": user_input,
        "history": history, # 完整的历史对话
        "neo4j_enabled": use_neo4j,
        "session_id": chat_id # 传递当前对话ID
    }
    print(f"发送给后端的负载: {json.dumps(payload, ensure_ascii=False)}") # 调试输出
    
    # 模拟网络延迟和后端处理
    # time.sleep(1.5) 

    # --- 在这里替换为真实的API调用 ---
    try:
        response = requests.post(BACKEND_API_URL, json=payload, timeout=120)
        print(f"后端响应: {response}") # 调试输出
        response.raise_for_status() # 如果HTTP错误 (4xx or 5xx) 则抛出异常
        backend_response = response.json()
        assistant_reply = backend_response.get("answer", "抱歉，后端没有返回有效的回答。")
        # 还可以从 backend_response 获取其他信息，如知识图谱检索结果等
    except requests.exceptions.RequestException as e:
        st.error(f"调用后端API失败: {e}")
        assistant_reply = "抱歉，与后端通信时发生错误，请稍后再试。"
    except json.JSONDecodeError:
        st.error("后端返回了无效的JSON格式。")
        assistant_reply = "抱歉，后端响应格式错误。"
    # --- 模拟回复 ---


    return assistant_reply

# --- 侧边栏 ---
with st.sidebar:
    st.image("https://streamlit.io/images/brand/streamlit-logo-secondary-colormark-darktext.svg", width=200) # 替换为您的Logo
    st.title("问答系统控制面板")
    st.markdown("---")

    # 新建对话按钮
    if st.button("🚀 新建对话", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "您好！我是中国先进知识问答助手，新对话已开始。"}]
        st.session_state.current_chat_id = f"chat_{int(time.time())}"
        st.toast("新的对话已开始！")
        st.rerun() # 重新运行脚本以刷新聊天区域

    st.markdown("---")
    # Neo4j 增强开关
    st.session_state.neo4j_enabled = st.toggle(
        "启用 Neo4j 知识增强", 
        value=st.session_state.neo4j_enabled, # 从session_state恢复上次的值
        help="启用后，系统将尝试使用知识图谱来增强回答的准确性和深度。"
    )
    if st.session_state.neo4j_enabled:
        st.info("Neo4j 知识增强已启用。")
    else:
        st.warning("Neo4j 知识增强已禁用。")
    
    st.markdown("---")
    st.markdown("### 关于系统")
    st.caption("本系统旨在提供关于中国先进技术领域的知识问答服务，结合了大型语言模型和知识图谱技术。")
    st.caption(f"当前对话ID: {st.session_state.current_chat_id}")


# --- 主聊天界面 ---
st.header("🇨🇳 中国先进知识问答系统")
st.caption("输入您的问题，与AI助手进行交流。")

# 初始化时显示欢迎语
if not st.session_state.messages:
    st.session_state.messages.append({"role": "assistant", "content": "您好！我是中国先进知识问答助手，有什么可以帮助您的吗？"})

# 显示历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 获取用户输入
if prompt := st.chat_input("请输入您的问题..."):
    # 1. 将用户消息添加到历史记录并显示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 调用后端API获取助手回复 (目前是模拟)
    with st.chat_message("assistant"):
        message_placeholder = st.empty() # 用于流式输出或显示"思考中..."
        message_placeholder.markdown("思考中...")
        
        # 准备发送给后端的历史记录 (可以根据需要调整，例如只发送最近N条)
        # 后端期望的可能是所有消息，或者有特定格式
        history_for_backend = st.session_state.messages[:-1] # 发送直到上一条用户消息为止的历史

        assistant_response = call_backend_api(
            user_input=prompt,
            history=history_for_backend, 
            use_neo4j=st.session_state.neo4j_enabled,
            chat_id=st.session_state.current_chat_id
        )
        message_placeholder.markdown(assistant_response) # 显示完整回复
    
    # 3. 将助手回复添加到历史记录
    st.session_state.messages.append({"role": "assistant", "content": assistant_response})

# --- UI 优化建议区 (可以在侧边栏或页面底部) ---
st.sidebar.markdown("---")
st.sidebar.subheader("💡 UI 提示与优化")
if st.sidebar.checkbox("显示调试信息"):
    st.sidebar.write("Session State:")
    st.sidebar.json(st.session_state.to_dict(), expanded=False)