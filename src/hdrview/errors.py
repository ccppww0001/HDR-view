"""项目共享的明确错误类型。"""


class HdrViewError(Exception):
    """所有可预期业务错误的基类。"""


class OutputConflictError(HdrViewError):
    """输出位置可能覆盖源文件或复用已有结果。"""


class SourceChangedError(HdrViewError):
    """源文件内容已不同于读取时记录的哈希。"""


class InvalidJpegError(HdrViewError):
    """JPEG 结构、声明偏移或私有尾部不可信。"""
