
from pydantic import BaseModel


class ComparisonStartRequest(BaseModel):
    standard_file_id: int
    comparison_file_id: int
    session_id: int | None = None
    title: str | None = None


class FileInfo(BaseModel):
    file_id: int
    title: str
    file_type: str
    download_url: str


class CharDiff(BaseModel):
    operation: str  # equal | replace | insert | delete
    std_text: str = ""
    cmp_text: str = ""


class ParagraphDiff(BaseModel):
    operation: str  # equal | modify | insert | delete
    std_index: int | None = None
    cmp_index: int | None = None
    standard_text: str = ""
    comparison_text: str = ""
    char_diff: list[CharDiff] = []


class DiffSummary(BaseModel):
    standard_paragraphs: int = 0
    comparison_paragraphs: int = 0
    difference_count: int = 0


class ComparisonResponse(BaseModel):
    task_id: int
    session_id: int
    diff_summary: DiffSummary
    diffs: list[ParagraphDiff]
    standard_file: FileInfo
    comparison_file: FileInfo
