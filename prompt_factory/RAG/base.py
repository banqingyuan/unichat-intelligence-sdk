from typing import List


InfoType_Knowledge = "knowledge"
InfoType_Scene = "scene"


class BaseInfoGetter:
    corpus_text: List[str]
    info_type: str

    def __call__(self, *args, **kwargs) -> str:
        raise NotImplementedError
