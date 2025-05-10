import openai
import json
import logging
import os
import time
import asyncio # For asynchronous API calls
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
import ijson # For streaming large JSON input

# --- 全局配置和常量 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("错误：请设置 OPENAI_API_KEY 环境变量。")
    exit(1)

# openai.api_key = OPENAI_API_KEY # For older openai versions
# For openai >= 1.0.0, client is initialized with api_key

MODEL_NAME = "gpt-3.5-turbo-0125" # Or your preferred model
INPUT_JSON_FILE = "./HaMmer/HaM_chinese_references.json" # From previous step
OUTPUT_JSON_FILE = "classified_chinese_references.json"
ERROR_JSON_FILE = "classification_errors.json" # For entries that failed classification
LOG_FILE = "classification_log.txt"

MAX_RETRIES = 5
API_TIMEOUT_SECONDS = 120  # Increased timeout for potentially long-running classifications
MAX_CONCURRENT_REQUESTS = 10 # Adjust based on your API rate limits and system capacity
TOPICS_LIST = [
    {"id": 1, "category_code": "I", "category_name": "新一代人工智能 (New Generation Artificial Intelligence)", "topic_name": "人工智能基础理论 (AI Fundamental Theory)", "description": "包括前沿基础理论突破、学习推理与决策等。"},
    {"id": 2, "category_code": "I", "category_name": "新一代人工智能 (New Generation Artificial Intelligence)", "topic_name": "AI核心技术与平台 (Core AI Technologies & Platforms)", "description": "包括深度学习框架、开源算法平台构建、自然语言处理、语音与视频处理、图像图形识别等。"},
    {"id": 3, "category_code": "I", "category_name": "新一代人工智能 (New Generation Artificial Intelligence)", "topic_name": "人工智能芯片与硬件 (AI Chips & Hardware)", "description": "侧重专用芯片研发。"},
    {"id": 4, "category_code": "II", "category_name": "量子信息 (Quantum Information)", "topic_name": "量子通信 (Quantum Communication)", "description": "包括城域、城际、自由空间量子通信技术。"},
    {"id": 5, "category_code": "II", "category_name": "量子信息 (Quantum Information)", "topic_name": "量子计算与模拟 (Quantum Computing & Simulation)", "description": "包括通用量子计算原型机、实用化量子模拟机研制。"},
    {"id": 6, "category_code": "II", "category_name": "量子信息 (Quantum Information)", "topic_name": "量子精密测量 (Quantum Metrology)", "description": "侧重量子精密测量技术突破。"},
    {"id": 7, "category_code": "III", "category_name": "集成电路 (Integrated Circuits)", "topic_name": "半导体设计与材料 (Semiconductor Design & Materials)", "description": "包括IC设计工具、关键装备、高纯靶材等。"},
    {"id": 8, "category_code": "III", "category_name": "集成电路 (Integrated Circuits)", "topic_name": "先进半导体工艺与器件 (Advanced Semiconductor Processes & Devices)", "description": "包括IGBT、MEMS、先进存储技术、宽禁带半导体（碳化硅、氮化镓等）。"},
    {"id": 9, "category_code": "IV", "category_name": "脑科学与类脑研究 (Brain Science and Brain-like Research)", "topic_name": "认知神经科学与脑图谱 (Cognitive Neuroscience & Brain Mapping)", "description": "包括认知原理分析、脑介观神经联接图谱绘制。"},
    {"id": 10, "category_code": "IV", "category_name": "脑科学与类脑研究 (Brain Science and Brain-like Research)", "topic_name": "脑疾病与神经发育 (Brain Disorders & Neural Development)", "description": "包括重大脑疾病机理与干预、儿童青少年脑智发育。"},
    {"id": 11, "category_code": "IV", "category_name": "脑科学与类脑研究 (Brain Science and Brain-like Research)", "topic_name": "脑机接口与类脑计算 (Brain-Computer Interface & Neuromorphic Computing)", "description": "包括类脑计算与脑机融合技术。"},
    {"id": 12, "category_code": "V", "category_name": "基因与生物技术 (Gene and Biotechnology)", "topic_name": "基因编辑与合成生物学 (Gene Editing & Synthetic Biology)", "description": "包括基因组学研究应用、遗传细胞与遗传育种、合成生物。"},
    {"id": 13, "category_code": "V", "category_name": "基因与生物技术 (Gene and Biotechnology)", "topic_name": "生物医药与诊断技术 (Biopharmaceuticals & Diagnostics)", "description": "包括生物药、抗体药物、创新疫苗、体外诊断技术。"},
    {"id": 14, "category_code": "V", "category_name": "基因与生物技术 (Gene and Biotechnology)", "topic_name": "农业与环境生物技术 (Agricultural & Environmental Biotechnology)", "description": "包括农作物、畜禽水产、农业微生物等重大新品种创制。"},
    {"id": 15, "category_code": "V", "category_name": "基因与生物技术 (Gene and Biotechnology)", "topic_name": "生物安全 (Biosafety)", "description": "侧重生物安全关键技术研究。"},
    {"id": 16, "category_code": "VI", "category_name": "临床医学与健康 (Clinical Medicine and Health)", "topic_name": "重大疾病机理与防治 (Major Disease Mechanisms & Control)", "description": "包括癌症、心脑血管、呼吸、代谢性疾病，重大传染病、慢性非传染性疾病防治。"},
    {"id": 17, "category_code": "VI", "category_name": "临床医学与健康 (Clinical Medicine and Health)", "topic_name": "前沿诊疗技术与再生医学 (Advanced Diagnostics/Therapeutics & Regenerative Medicine)", "description": "包括主动健康干预、再生医学、微生物组、新型治疗等前沿技术。"},
    {"id": 18, "category_code": "VII", "category_name": "深空深海和极地探测 (Deep Space, Deep Sea, and Polar Exploration)", "topic_name": "深空探测与行星科学 (Deep Space Exploration & Planetary Science)", "description": "包括宇宙起源演化、火星环境、小行星巡视等。"},
    {"id": 19, "category_code": "VII", "category_name": "深空深海和极地探测 (Deep Space, Deep Sea, and Polar Exploration)", "topic_name": "深海与极地科学技术 (Deep Sea & Polar Science/Technology)", "description": "包括深海运载、观测、保障装备，极地立体观测平台、破冰船等。"},
    {"id": 20, "category_code": "VIII", "category_name": "数理科学 (Mathematical and Physical Sciences)", "topic_name": "基础数学前沿 (Frontiers of Fundamental Mathematics)", "description": "包括数论、代数几何、微分方程、随机分析等。"},
    {"id": 21, "category_code": "IX", "category_name": "化学科学 (Chemical Sciences)", "topic_name": "合成化学与催化 (Synthetic Chemistry & Catalysis)", "description": "包括精准合成、绿色合成、高效催化、反应机理等。"},
    {"id": 22, "category_code": "IX", "category_name": "化学科学 (Chemical Sciences)", "topic_name": "表界面化学与材料 (Surface/Interface Chemistry & Materials)", "description": "包括表界面结构、分子组装、外场调控等。"}
]

VALID_TOPIC_IDS = {topic['id'] for topic in TOPICS_LIST}
TOPIC_ID_TO_NAME_MAP = {topic['id']: topic['topic_name'] for topic in TOPICS_LIST}
# (TOPICS_LIST, VALID_TOPIC_IDS, TOPIC_ID_TO_NAME_MAP defined as above)

# --- 日志配置 ---
def setup_logging(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(levelname)s - %(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    # File handler
    try:
        fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)
    except Exception as e:
        logger.error(f"无法配置日志文件处理器: {e}")
    return logger

logger = setup_logging(LOG_FILE)

# --- 主题和Prompt辅助函数 ---
def get_topics_description_string():
    """Formats the topics list for inclusion in the prompt."""
    description = "以下是所有可选的主题列表：\n"
    for topic in TOPICS_LIST:
        description += f"ID: {topic['id']}, 主题大类: {topic['category_name']}, 具体主题: {topic['topic_name']}, 描述: {topic['description']}\n"
    return description

TOPICS_DESCRIPTION_STRING = get_topics_description_string()

def build_prompt_messages(entry):
    """Builds the prompt messages for the OpenAI API call."""
    title = entry.get("Title", "N/A")
    keywords_list = entry.get("Keywords", [])
    keywords = ", ".join(keywords_list) if isinstance(keywords_list, list) else "N/A"
    abstract = entry.get("Abstract", "N/A")
    
    # Check for patent-specific subject information
    patent_subject_info = ""
    # You might need to adjust "Patent" if your "Reference Type" field uses different terms for patents
    if "patent" in entry.get("Reference Type", "").lower() or "专利" in entry.get("Reference Type", ""):
        subject = entry.get("Subject") # Assuming 'Subject' is the field name for patent subjects
        if subject:
            patent_subject_info = f"\n专利主题分类信息：{subject}"

    system_message = "您是一位专业的科研文献分类助手。您的任务是根据提供的文献信息（标题、关键词、摘要，以及可能的专利主题），将其准确地分配到预定义的科研主题中。请只选择一个最相关的主题。"
    
    user_prompt = f"""{TOPICS_DESCRIPTION_STRING}
请仔细分析以下文献信息：
文献标题：{title}
文献关键词：{keywords}
文献摘要：{abstract}{patent_subject_info}

请严格按照以下JSON格式返回您的分类结果，并且只返回这个JSON对象：
{{
  "topic_id": <主题的数字ID>,
  "topic_name": "<对应主题的完整具体主题名称>"
}}
确保 'topic_id' 是一个整数，并且 'topic_name' 是所选主题的准确名称。从上述列表中选择一个最匹配的主题。
"""
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt}
    ]

# --- OpenAI API 调用函数 (异步) ---
# Define custom exception for retry logic if needed, or use existing ones.
RETRYABLE_EXCEPTIONS = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.InternalServerError,
    # openai.APIStatusError, # Some status errors might be retryable (e.g., 502, 503, 504)
    # requests.exceptions.Timeout, # If using requests directly
    # requests.exceptions.ConnectionError
)

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=60), # Exponential backoff
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before_sleep=lambda retry_state: logger.warning(f"API调用重试: 第 {retry_state.attempt_number} 次尝试，因为 {retry_state.outcome.exception()}"),
    reraise=True # Reraise the exception if all retries fail
)
async def get_classification_from_openai_async(client, messages, entry_identifier="未知条目"):
    """
    Asynchronously calls the OpenAI API for classification with retry logic.
    """
    try:
        logger.debug(f"[{entry_identifier}] 正在为条目发送API请求。Prompt长度（估算字符数）: {len(str(messages))}")
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.0, # Low temperature for deterministic classification
            response_format={"type": "json_object"}, # Enable JSON mode
            timeout=API_TIMEOUT_SECONDS
        )
        response_content = completion.choices[0].message.content
        logger.debug(f"[{entry_identifier}] API原始响应: {response_content}")
        
        # Parse the JSON response from the model
        try:
            classification_result = json.loads(response_content)
        except json.JSONDecodeError as e:
            logger.error(f"[{entry_identifier}] API响应JSON解析失败: {e}. 响应内容: {response_content}")
            # This case is problematic even with JSON mode, might indicate a malformed string within the JSON
            return {"error": "API response JSON parsing failed", "details": str(e), "raw_response": response_content}

        # Validate the structure and content of the classification
        if not isinstance(classification_result, dict) or \
           "topic_id" not in classification_result or \
           "topic_name" not in classification_result:
            logger.error(f"[{entry_identifier}] API响应JSON结构无效: {classification_result}")
            return {"error": "Invalid JSON structure from API", "raw_response": classification_result}

        topic_id = classification_result.get("topic_id")
        if not isinstance(topic_id, int) or topic_id not in VALID_TOPIC_IDS:
            logger.warning(f"[{entry_identifier}] API返回了无效的topic_id: {topic_id}. 响应: {classification_result}")
            # You might decide to still keep the raw response or mark as error
            return {"error": "Invalid topic_id from API", "topic_id_received": topic_id, "raw_response": classification_result}
        
        # Optional: Verify topic_name matches the id (or trust the model if id is valid)
        expected_topic_name = TOPIC_ID_TO_NAME_MAP.get(topic_id)
        if classification_result.get("topic_name") != expected_topic_name:
             logger.warning(f"[{entry_identifier}] API返回的topic_name与ID不完全匹配。ID: {topic_id}, 返回名称: '{classification_result.get('topic_name')}', 期望名称: '{expected_topic_name}'. 将使用ID对应的期望名称。")
             classification_result["topic_name"] = expected_topic_name # Correct it

        return classification_result

    except openai.BadRequestError as e: # Non-retryable client-side error (e.g. bad prompt, context length)
        logger.error(f"[{entry_identifier}] OpenAI API BadRequestError (不可重试): {e}")
        return {"error": "OpenAI API BadRequestError", "details": str(e)}
    except RetryError as e: # All retries failed
        logger.error(f"[{entry_identifier}] API调用在 {MAX_RETRIES} 次重试后最终失败: {e}")
        return {"error": "API call failed after multiple retries", "details": str(e)}
    except Exception as e: # Catch any other unexpected errors during API call
        logger.error(f"[{entry_identifier}] API调用时发生未知错误: {e}", exc_info=True)
        return {"error": "Unknown API call error", "details": str(e)}


# --- 主处理函数 (异步) ---
async def main_classification_process():
    logger.info(f"开始对文件 '{INPUT_JSON_FILE}' 中的文献进行主题分类...")
    logger.info(f"使用模型: {MODEL_NAME}")
    logger.info(f"分类结果将保存到: {OUTPUT_JSON_FILE}")
    logger.info(f"处理失败的条目将保存到: {ERROR_JSON_FILE}")

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS + 10, base_url="https://api.lqqq.ltd/v1") # client timeout slightly higher
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS) # Limit concurrent API calls

    processed_count = 0
    success_count = 0
    error_count = 0
    
    output_file_empty = True
    error_file_empty = True

    try:
        with open(INPUT_JSON_FILE, 'rb') as f_in, \
             open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f_out, \
             open(ERROR_JSON_FILE, 'w', encoding='utf-8') as f_err:
            
            f_out.write("[\n") # Start of the JSON list for successful items
            f_err.write("[\n") # Start of the JSON list for error items

            # Use ijson to stream-parse the input JSON file
            # The `item` prefix means we are expecting a list of objects at the root
            json_items = ijson.items(f_in, 'item') 
            
            tasks = []
            entries_buffer = [] # Buffer to hold entries for which tasks are created

            # Estimate total items for tqdm if possible (ijson doesn't easily give total count beforehand for very large files)
            # For a true count, you might need a pre-pass or assume a large number for tqdm if the file is huge.
            # If INPUT_JSON_FILE is not excessively large, a quick pre-count can be done.
            # For now, tqdm will show iterations.
            
            # Create a tqdm instance that we can manually update if we get total count later
            pbar = tqdm(desc="处理文献条目", unit="条")

            for entry in json_items: # This iterates through each object in the JSON array
                pbar.update(1) # Update progress for each item read
                processed_count += 1
                entry_id_for_log = entry.get("Title", f"条目_{processed_count}")[:50] # Short identifier for logs

                messages = build_prompt_messages(entry)
                
                # Store the original entry to write it out later with classification
                entries_buffer.append(entry) 
                
                task = asyncio.ensure_future(classify_entry_with_semaphore(client, messages, entry_id_for_log, semaphore))
                tasks.append(task)

                if len(tasks) >= MAX_CONCURRENT_REQUESTS * 2 : # Process tasks in batches to manage memory for entries_buffer
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for original_entry, result in zip(entries_buffer, results):
                        entry_id = original_entry.get("Title", "未知标题")[:50]
                        if isinstance(result, Exception) or (isinstance(result, dict) and "error" in result):
                            logger.error(f"条目 '{entry_id}' 分类失败: {result}")
                            error_count += 1
                            original_entry["classification_error"] = str(result) if not isinstance(result, dict) else result
                            if not error_file_empty:
                                f_err.write(",\n")
                            json.dump(original_entry, f_err, ensure_ascii=False, indent=2)
                            error_file_empty = False
                        else:
                            success_count += 1
                            original_entry["classification"] = result
                            if not output_file_empty:
                                f_out.write(",\n")
                            json.dump(original_entry, f_out, ensure_ascii=False, indent=2)
                            output_file_empty = False
                    tasks = []
                    entries_buffer = []
            
            # Process any remaining tasks
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for original_entry, result in zip(entries_buffer, results):
                    entry_id = original_entry.get("Title", "未知标题")[:50]
                    if isinstance(result, Exception) or (isinstance(result, dict) and "error" in result):
                        logger.error(f"条目 '{entry_id}' 分类失败: {result}")
                        error_count += 1
                        original_entry["classification_error"] = str(result) if not isinstance(result, dict) else result
                        if not error_file_empty:
                            f_err.write(",\n")
                        json.dump(original_entry, f_err, ensure_ascii=False, indent=2)
                        error_file_empty = False
                    else:
                        success_count += 1
                        original_entry["classification"] = result
                        if not output_file_empty:
                            f_out.write(",\n")
                        json.dump(original_entry, f_out, ensure_ascii=False, indent=2)
                        output_file_empty = False
            pbar.close()

            if not output_file_empty: f_out.write("\n")
            f_out.write("]\n")
            if not error_file_empty: f_err.write("\n")
            f_err.write("]\n")

    except FileNotFoundError:
        logger.error(f"错误: 输入文件 '{INPUT_JSON_FILE}' 未找到。")
        return
    except ijson.JSONError as e:
        logger.error(f"错误: 解析输入JSON文件 '{INPUT_JSON_FILE}' 失败: {e}")
        return
    except Exception as e:
        logger.error(f"处理过程中发生严重错误: {e}", exc_info=True)
    finally:
        logger.info("--- 分类处理完成 ---")
        logger.info(f"总共读取的文献条目数: {processed_count}")
        logger.info(f"成功分类的文献条目数: {success_count}")
        logger.info(f"分类失败的文献条目数: {error_count}")
        logger.info(f"详细日志请查看: {LOG_FILE}")
        logger.info(f"成功结果保存在: {OUTPUT_JSON_FILE}")
        logger.info(f"失败条目保存在: {ERROR_JSON_FILE}")

async def classify_entry_with_semaphore(client, messages, entry_identifier, semaphore):
    """Helper function to acquire semaphore before calling API."""
    async with semaphore:
        return await get_classification_from_openai_async(client, messages, entry_identifier)

# --- 运行入口 ---
if __name__ == "__main__":
    if not os.path.exists(INPUT_JSON_FILE):
        logger.error(f"错误：输入文件 '{INPUT_JSON_FILE}' 不存在。请先执行上一步生成该文件。")
    else:
        start_time = time.time()
        try:
            asyncio.run(main_classification_process())
        except KeyboardInterrupt:
            logger.info("用户手动中断程序执行。")
        finally:
            end_time = time.time()
            logger.info(f"总执行耗时: {end_time - start_time:.2f} 秒")