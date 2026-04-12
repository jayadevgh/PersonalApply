from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    platform: str

    @abstractmethod
    def open_application(self, job: dict) -> None:
        pass

    @abstractmethod
    def fill_known_fields(self, job: dict) -> None:
        pass

    @abstractmethod
    def find_unknown_questions(self, job: dict) -> list[dict]:
        pass

    @abstractmethod
    def submit(self, job: dict) -> None:
        pass
