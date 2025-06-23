# app/api/v1/schemas.py
from pydantic import BaseModel, Field
from typing import List

class ResultFile(BaseModel):
    filename: str
    url: str

class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Уникальный идентификатор задачи.")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="Статус задачи: pending, processing, completed, failed.")
    results: List[ResultFile] = Field([], description="Список файлов с результатами.")