from abc import ABC, abstractmethod
from typing import Dict, Generator, Tuple


class BaseScene(ABC):
    scene_id: str
    display_name: str

    @abstractmethod
    def create_state(self):
        raise NotImplementedError

    @abstractmethod
    def get_role_info(self, role_key: str) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def run_turn(self, user_message: str, state) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def stream_turn(self, user_message: str, state) -> Tuple[Dict, Generator[str, None, None]]:
        raise NotImplementedError

    @abstractmethod
    def serialize_state(self, state) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def deserialize_state(self, payload: Dict):
        raise NotImplementedError
