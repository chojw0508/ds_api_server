import os
import json
import logging
from datetime import datetime
from fastapi import HTTPException
import openai

from services.text_embedding import TextEmbeddings
from services.vector_service import milvus_search
from core.messages import ServerMessages

logger = logging.getLogger("uvicorn.error")


class ChatBot:
    """ChatGPT 기반 챗봇 서비스."""

    def __init__(self, config, initialize_db):
        self.config = config
        self.initialize_db = initialize_db
        self.redis = initialize_db.redis_client
        self.mongo = initialize_db.mongo_client[config.mongodb.database][config.mongodb.collection]
        self.redis_prefix = "history:"
        self.embedding = TextEmbeddings()
        openai.api_key = os.getenv("OPENAI_API_KEY")

    def _get_history(self, session_id: str):
        """Retrieve conversation history from Redis or MongoDB."""
        redis_key = f"{self.redis_prefix}{session_id}"
        if self.redis.exists(redis_key):
            data = self.redis.lrange(redis_key, 0, -1)
            return [json.loads(item) for item in data]

        records = list(self.mongo.find({"session_id": session_id}).sort("timestamp", 1))
        for rec in records:
            msg = {"role": rec["role"], "content": rec["content"]}
            self.redis.rpush(redis_key, json.dumps(msg))
        return records

    def _save_message(self, session_id: str, role: str, content: str):
        """Save a chat message to MongoDB and Redis."""
        doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
        }
        self.mongo.insert_one(doc)
        self.redis.rpush(f"{self.redis_prefix}{session_id}", json.dumps({"role": role, "content": content}))

    def chat_with_session(self, session_id: str, user_message: str, use_rag: bool, collection: str, top_k: int):
        try:
            if not self.redis.exists(session_id):
                self.redis.set(session_id, "1")

            history = self._get_history(session_id)
            messages = [{"role": h["role"], "content": h["content"]} for h in history]
            messages.append({"role": "user", "content": user_message})

            if use_rag:
                embedded = self.embedding.get_embeddings([user_message])
                result = milvus_search(collection, "COSINE", 10, embedded, top_k, ["text"])
                docs = "\n".join(hit.entity.get("text", "") for hit in result[0])
                if docs:
                    messages.append({"role": "system", "content": f"Reference:\n{docs}"})

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            answer = response.choices[0].message.content

            self._save_message(session_id, "user", user_message)
            self._save_message(session_id, "assistant", answer)

            return {"answer": answer}
        except Exception as e:
            logger.error(ServerMessages.CHAT_REQUEST_ERROR + f"{e}")
            raise HTTPException(status_code=500, detail=ServerMessages.CHAT_REQUEST_ERROR)

    def chat_test(self, messages: list[dict], use_rag: bool, collection: str, top_k: int):
        """사용자 정보 없이 대화 메시지 목록만으로 답변을 생성합니다."""
        try:
            conv = messages.copy()
            if use_rag and messages:
                user_msg = messages[-1].get("content", "")
                embedded = self.embedding.get_embeddings([user_msg])
                result = milvus_search(collection, "COSINE", 10, embedded, top_k, ["text"])
                docs = "\n".join(hit.entity.get("text", "") for hit in result[0])
                if docs:
                    conv.append({"role": "system", "content": f"Reference:\n{docs}"})

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=conv
            )
            answer = response.choices[0].message.content
            return {"answer": answer}
        except Exception as e:
            logger.error(ServerMessages.CHAT_REQUEST_ERROR + f"{e}")
            raise HTTPException(status_code=500, detail=ServerMessages.CHAT_REQUEST_ERROR)
