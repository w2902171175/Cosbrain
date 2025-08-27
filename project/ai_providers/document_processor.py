# ai_providers/document_processor.py
"""
文档处理模块
包含文档解析、文本提取、文本分块等功能
"""
import io
import re
from typing import List, Optional, Dict, Any
import PyPDF2
from docx import Document as DocxDocument

from .embedding_provider import create_embedding_provider


def _clean_text(text: str) -> str:
    """清理文本，去除多余空格和换行"""
    if not text:
        return ""
    
    # 去除多余的空白字符
    text = re.sub(r'\s+', ' ', text.strip())
    return text


def _split_text_by_sentences(text: str) -> List[str]:
    """按句子分割文本"""
    if not text:
        return []
    
    # 使用正则表达式分割句子
    sentences = re.split(r'[。！？.!?]+', text)
    # 过滤空句子
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


class DocumentProcessor:
    """文档处理器类"""
    
    def __init__(self, provider_type: str = "siliconflow", api_key: Optional[str] = None):
        """
        初始化文档处理器
        
        Args:
            provider_type: 嵌入向量提供者类型
            api_key: API密钥
        """
        self.provider_type = provider_type
        self.api_key = api_key
        self.embedding_provider = None
        
        if api_key:
            try:
                self.embedding_provider = create_embedding_provider(provider_type, api_key)
            except Exception as e:
                print(f"WARNING: 无法创建嵌入向量提供者: {e}")
    
    def extract_content(self, file_content_bytes: bytes, file_type: str) -> str:
        """提取文档内容"""
        return extract_text_from_document(file_content_bytes, file_type)
    
    async def process_document(self, file_content_bytes: bytes, file_type: str, chunk_size: int = 1000) -> List[Dict[str, Any]]:
        """
        处理文档并生成向量化的文本块
        
        Args:
            file_content_bytes: 文件内容
            file_type: 文件类型
            chunk_size: 文本块大小
            
        Returns:
            包含文本和嵌入向量的文档块列表
        """
        # 提取文本
        text = self.extract_content(file_content_bytes, file_type)
        
        # 分块
        chunks = chunk_text(text, chunk_size)
        
        # 生成嵌入向量
        if self.embedding_provider:
            try:
                embeddings = await self.embedding_provider.get_embeddings(chunks)
                return [
                    {"text": chunk, "embedding": embedding}
                    for chunk, embedding in zip(chunks, embeddings)
                ]
            except Exception as e:
                print(f"WARNING: 无法生成嵌入向量: {e}")
        
        # 如果无法生成嵌入向量，返回纯文本块
        return [{"text": chunk, "embedding": None} for chunk in chunks]


def extract_text_from_document(file_content_bytes: bytes, file_type: str) -> str:
    """
    从文档中提取文本内容
    
    Args:
        file_content_bytes: 文件字节内容
        file_type: 文件类型 (pdf, docx, txt)
        
    Returns:
        提取的文本内容
    """
    try:
        if file_type.lower() == "pdf":
            return _extract_text_from_pdf(file_content_bytes)
        elif file_type.lower() in ["docx", "doc"]:
            return _extract_text_from_docx(file_content_bytes)
        elif file_type.lower() == "txt":
            return _extract_text_from_txt(file_content_bytes)
        else:
            print(f"WARNING: 不支持的文件类型: {file_type}")
            return ""
    except Exception as e:
        print(f"ERROR: 文档文本提取失败: {e}")
        return ""


def _extract_text_from_pdf(file_content_bytes: bytes) -> str:
    """从PDF文件中提取文本"""
    try:
        pdf_file = io.BytesIO(file_content_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        
        text_content = []
        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text.strip():
                    text_content.append(page_text)
            except Exception as e:
                print(f"WARNING: 无法提取PDF第{page_num + 1}页的文本: {e}")
                continue
        
        return "\n\n".join(text_content)
    except Exception as e:
        print(f"ERROR: PDF文本提取失败: {e}")
        return ""


def _extract_text_from_docx(file_content_bytes: bytes) -> str:
    """从DOCX文件中提取文本"""
    try:
        docx_file = io.BytesIO(file_content_bytes)
        doc = DocxDocument(docx_file)
        
        text_content = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_content.append(paragraph.text)
        
        return "\n\n".join(text_content)
    except Exception as e:
        print(f"ERROR: DOCX文本提取失败: {e}")
        return ""


def _extract_text_from_txt(file_content_bytes: bytes) -> str:
    """从TXT文件中提取文本"""
    try:
        # 尝试不同的编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        for encoding in encodings:
            try:
                return file_content_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，使用utf-8并忽略错误
        return file_content_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"ERROR: TXT文本提取失败: {e}")
        return ""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    将长文本分割成指定大小的块
    
    Args:
        text: 要分割的文本
        chunk_size: 每个块的大小（字符数）
        overlap: 块之间的重叠字符数
        
    Returns:
        文本块列表
    """
    if not text or not text.strip():
        return []
    
    text = text.strip()
    
    # 如果文本长度小于块大小，直接返回
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        # 确定当前块的结束位置
        end = start + chunk_size
        
        # 如果不是最后一块，尝试在句号、换行符或空格处断开
        if end < len(text):
            # 在合理范围内寻找自然断点
            search_range = min(100, chunk_size // 4)  # 搜索范围为块大小的1/4或100字符
            
            # 首先尝试在句号处断开
            period_pos = text.rfind('。', end - search_range, end)
            if period_pos != -1:
                end = period_pos + 1
            else:
                # 尝试在换行符处断开
                newline_pos = text.rfind('\n', end - search_range, end)
                if newline_pos != -1:
                    end = newline_pos
                else:
                    # 最后尝试在空格处断开
                    space_pos = text.rfind(' ', end - search_range, end)
                    if space_pos != -1:
                        end = space_pos
        
        # 提取当前块
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # 计算下一块的起始位置（考虑重叠）
        if end >= len(text):
            break
        
        start = max(start + 1, end - overlap)
    
    return chunks


def clean_text(text: str) -> str:
    """
    清理文本，移除多余的空白字符和特殊字符
    
    Args:
        text: 要清理的文本
        
    Returns:
        清理后的文本
    """
    if not text:
        return ""
    
    # 替换多个空白字符为单个空格
    text = re.sub(r'\s+', ' ', text)
    
    # 移除开头和结尾的空白字符
    text = text.strip()
    
    return text


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """
    从文本中提取关键词（简单实现）
    
    Args:
        text: 输入文本
        max_keywords: 最大关键词数量
        
    Returns:
        关键词列表
    """
    if not text:
        return []
    
    # 简单的关键词提取：移除停用词，按词频排序
    # 这里是一个简化版本，实际应用中可以使用更复杂的NLP技术
    
    # 移除标点符号并转换为小写
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    
    # 分词
    words = text.split()
    
    # 简单的中文停用词
    stop_words = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '那', '这个', '那个', '可以', '这样', '如果', '因为', '所以'
    }
    
    # 过滤停用词和短词
    filtered_words = [
        word for word in words 
        if len(word) > 1 and word not in stop_words
    ]
    
    # 计算词频
    word_freq = {}
    for word in filtered_words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # 按频率排序并返回前N个
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    
    return [word for word, freq in sorted_words[:max_keywords]]
