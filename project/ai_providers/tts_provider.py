# ai_providers/tts_provider.py
"""
TTS服务提供者实现
"""
import io
from typing import Optional
from gtts import gTTS
from openai import AsyncOpenAI
from .ai_base import TTSProvider
from .ai_config import DEFAULT_TTS_CONFIGS


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS服务提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
        
        config = DEFAULT_TTS_CONFIGS["openai"]
        self.base_url = base_url or config["base_url"]
        self.default_model = config["default_model"]
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)
    
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "alloy",
        model: Optional[str] = None,
        language: str = "zh-CN"
    ) -> bytes:
        """使用OpenAI TTS合成语音"""
        try:
            response = await self.client.audio.speech.create(
                model=model or self.default_model,
                voice=voice,
                input=text
            )
            
            # 返回音频数据
            return response.content
            
        except Exception as e:
            print(f"ERROR_OPENAI_TTS: OpenAI TTS 错误: {e}")
            raise


class GTTSProvider(TTSProvider):
    """Google Text-to-Speech (gTTS) 提供者"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
    
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "alloy",
        model: Optional[str] = None,
        language: str = "zh-CN"
    ) -> bytes:
        """使用gTTS合成语音"""
        try:
            # 语言代码映射
            lang_map = {
                "zh-CN": "zh",
                "en-US": "en",
                "ja-JP": "ja",
                "ko-KR": "ko"
            }
            
            lang = lang_map.get(language, "zh")
            
            # 创建gTTS对象
            tts = gTTS(text=text, lang=lang, slow=False)
            
            # 将音频数据写入内存
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            return audio_buffer.read()
            
        except Exception as e:
            print(f"ERROR_GTTS: gTTS 错误: {e}")
            raise


def create_tts_provider(
    provider_type: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> TTSProvider:
    """
    TTS提供者工厂函数
    
    Args:
        provider_type: 提供者类型
        api_key: API密钥（可选，gTTS不需要）
        base_url: API基础URL（可选）
        
    Returns:
        TTS提供者实例
    """
    if provider_type == "openai":
        if not api_key:
            raise ValueError("OpenAI TTS 需要提供 API 密钥")
        return OpenAITTSProvider(api_key, base_url)
    elif provider_type == "default_gtts":
        return GTTSProvider()
    else:
        raise ValueError(f"不支持的TTS提供者类型: {provider_type}")
