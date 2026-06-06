from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional

class UserDTO(BaseModel):
    """
    Data Transfer Object used across Producer and Consumer.
    Ensures input data structure is valid before pushing to MQ or DB.
    """
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    age: int = Field(default=18, ge=0, le=150)
    status: int = Field(default=1, description="1: Active, 0: Inactive")
    
    # Metadata fields (standard in large architectures)
    # We will let the DB auto-generate timestamps, or pass them if provided
    # but here we allow them optional in DTO.

    from pydantic import ConfigDict
    model_config = ConfigDict(from_attributes=True)
