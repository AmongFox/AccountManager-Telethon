from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    message: Optional[str] = None
    data: str
