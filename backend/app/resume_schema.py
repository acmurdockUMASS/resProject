from pydantic import BaseModel, Field
from typing import List

class Header(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    location: str = ""

class EducationEntry(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    grad: str = ""
    gpa: str = ""
    coursework: List[str] = Field(default_factory=list)

class RoleEntry(BaseModel):
    company: str = ""
    location: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    bullets: List[str] = Field(default_factory=list)

class ProjectEntry(BaseModel):
    name: str = ""
    link: str = ""
    stack: List[str] = Field(default_factory=list)
    start: str = ""
    end: str = ""
    bullets: List[str] = Field(default_factory=list)

class LeadershipEntry(BaseModel):
    org: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    bullets: List[str] = Field(default_factory=list)

class Skills(BaseModel):
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)

class Resume(BaseModel):
    header: Header = Field(default_factory=Header)
    education: List[EducationEntry] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    experience: List[RoleEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    leadership: List[LeadershipEntry] = Field(default_factory=list)
    awards: List[str] = Field(default_factory=list)