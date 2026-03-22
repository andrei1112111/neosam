from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Static
from rich.text import Text
from rich.console import RenderableType
from time import time
from asyncio import create_task, sleep


class CodeBlock(Widget):
    """Виджет для отображения кода с подсветкой"""
    
    def __init__(self, code: str, language: str = "bash") -> None:
        super().__init__()
        self._code = code
        self._language = language
    
    def render(self) -> RenderableType:
        return Text(self._code, style="bold cyan", justify="left")


class LargeHello(Widget):
    """Отображение приветствия большим текстом."""
    
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
    
    def render(self) -> RenderableType:
        # Создаем большой текст с помощью Rich
        return Text(self._text, style="bold", justify="center")

class InstallationGuide_macos(Widget):
    DEFAULT_CSS = """
    WelcomePage {
        width: 100%;
        height: 100%;
    }

    #welcome-layout {
        width: 100%;
        height: 100%;
    }

    #welcome-stack {
        width: 100%;
        height: 100%;
    }

    #welcome-index {
        width: auto;
        content-align: left top;
        text-style: bold;
        margin: 1 0 0 1;
    }

    /* Скроллируемый контейнер для контента */
    .scroll-container {
        width: 100%;
        height: auto;
        overflow-y: auto;
    }

    /* Контейнер для центрирования контента */
    .content-container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
    }

    /* Стиль для большого приветствия */
    LargeHello {
        width: 100%;
        height: auto;
        color: $text;
        border: none;
        content-align: center middle;
        padding: 1;
    }

    /* Стиль для дополнительного виджета */
    .additional-widget {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text;
        border: none;
        content-align: center middle;
        margin-top: 1;
    }

    /* Стиль для анимированных кнопок */
    AnimatedAsciiButtons {
        width: 100%;
        height: auto;
        padding: 1 2;
        content-align: center middle;
        margin-top: 1;
    }

    /* Распорка сверху */
    #top-spacer {
        height: 1fr;
    }

    /* Распорка снизу, которая выталкивает кнопки вниз */
    #bottom-spacer {
        height: 1fr;
    }

    #bottom-margin {
        height: 2vh;
    }

    #welcome-controls {
        width: 100%;
        height: 3;
        align-horizontal: center;
    }

    #startup-next {
        border: none;
        background: transparent;
        text-style: bold;
    }
    #startup-prev {
        border: none;
        background: transparent;
        text-style: bold;
    }
    /* Стиль для кода */
    CodeBlock {
        width: 100%;
        height: auto;
        padding: 1 2;
        background: $surface;
        color: $text;
        border: solid $primary;
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-layout"):
            with Vertical(id="welcome-stack"):
                yield Static("установка на <MACOS> linux windows", id="welcome-index")
                
                # Распорка сверху
                yield Static(id="top-spacer")
                
                # Скроллируемый контейнер для контента
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("Установка i2p через homebrew:")

                        yield Static("1: Установка Homebrew", classes="step")
                        yield CodeBlock('bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
                        
                        
                        yield Static("2: Установка i2pd", classes="step")
                        yield CodeBlock("brew install i2pd")

                        yield Static("3: Запуск роутера i2pd. Подключение к i2p сети", classes="step")
                        yield CodeBlock("i2pd --http.address=127.0.0.1 --http.port=7070 --sam.enabled=1 --sam.port=7656")
                        yield Static("Для отсановки", classes="step")
                        yield CodeBlock("brew services stop i2pd")


                # Распорка снизу
                yield Static(id="bottom-spacer")
                
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next")
                
                yield Static(id="bottom-margin")


class InstallationGuide_linux(Widget):
    DEFAULT_CSS = """
    WelcomePage {
        width: 100%;
        height: 100%;
    }

    #welcome-layout {
        width: 100%;
        height: 100%;
    }

    #welcome-stack {
        width: 100%;
        height: 100%;
    }

    #welcome-index {
        width: auto;
        content-align: left top;
        text-style: bold;
        margin: 1 0 0 1;
    }

    /* Скроллируемый контейнер для контента */
    .scroll-container {
        width: 100%;
        height: auto;
        overflow-y: auto;
    }

    /* Контейнер для центрирования контента */
    .content-container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
    }

    /* Стиль для большого приветствия */
    LargeHello {
        width: 100%;
        height: auto;
        color: $text;
        border: none;
        content-align: center middle;
        padding: 1;
    }

    /* Стиль для дополнительного виджета */
    .additional-widget {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text;
        border: none;
        content-align: center middle;
        margin-top: 1;
    }

    /* Стиль для анимированных кнопок */
    AnimatedAsciiButtons {
        width: 100%;
        height: auto;
        padding: 1 2;
        content-align: center middle;
        margin-top: 1;
    }

    /* Распорка сверху */
    #top-spacer {
        height: 1fr;
    }

    /* Распорка снизу, которая выталкивает кнопки вниз */
    #bottom-spacer {
        height: 1fr;
    }

    #bottom-margin {
        height: 2vh;
    }

    #welcome-controls {
        width: 100%;
        height: 3;
        align-horizontal: center;
    }

    #startup-next {
        border: none;
        background: transparent;
        text-style: bold;
    }
    #startup-prev {
        border: none;
        background: transparent;
        text-style: bold;
    }
    /* Стиль для кода */
    CodeBlock {
        width: 100%;
        height: auto;
        padding: 1 2;
        background: $surface;
        color: $text;
        border: solid $primary;
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-layout"):
            with Vertical(id="welcome-stack"):
                yield Static("установка на macos <LINUX>, windows", id="welcome-index")
                
                # Распорка сверху
                yield Static(id="top-spacer")
                
                # Скроллируемый контейнер для контента
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("НЕ ТЕСТИРОВАЛОСЬ")


                # Распорка снизу
                yield Static(id="bottom-spacer")
                
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next")
                
                yield Static(id="bottom-margin")


class InstallationGuide_windown(Widget):
    DEFAULT_CSS = """
    WelcomePage {
        width: 100%;
        height: 100%;
    }

    #welcome-layout {
        width: 100%;
        height: 100%;
    }

    #welcome-stack {
        width: 100%;
        height: 100%;
    }

    #welcome-index {
        width: auto;
        content-align: left top;
        text-style: bold;
        margin: 1 0 0 1;
    }

    /* Скроллируемый контейнер для контента */
    .scroll-container {
        width: 100%;
        height: auto;
        overflow-y: auto;
    }

    /* Контейнер для центрирования контента */
    .content-container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
    }

    /* Стиль для большого приветствия */
    LargeHello {
        width: 100%;
        height: auto;
        color: $text;
        border: none;
        content-align: center middle;
        padding: 1;
    }

    /* Стиль для дополнительного виджета */
    .additional-widget {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text;
        border: none;
        content-align: center middle;
        margin-top: 1;
    }

    /* Стиль для анимированных кнопок */
    AnimatedAsciiButtons {
        width: 100%;
        height: auto;
        padding: 1 2;
        content-align: center middle;
        margin-top: 1;
    }

    /* Распорка сверху */
    #top-spacer {
        height: 1fr;
    }

    /* Распорка снизу, которая выталкивает кнопки вниз */
    #bottom-spacer {
        height: 1fr;
    }

    #bottom-margin {
        height: 2vh;
    }

    #welcome-controls {
        width: 100%;
        height: 3;
        align-horizontal: center;
    }

    #startup-next {
        border: none;
        background: transparent;
        text-style: bold;
    }
    #startup-prev {
        border: none;
        background: transparent;
        text-style: bold;
    }
    /* Стиль для кода */
    CodeBlock {
        width: 100%;
        height: auto;
        padding: 1 2;
        background: $surface;
        color: $text;
        border: solid $primary;
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-layout"):
            with Vertical(id="welcome-stack"):
                yield Static("установка на macos linux <WINDOWS>", id="welcome-index")
                
                # Распорка сверху
                yield Static(id="top-spacer")
                
                # Скроллируемый контейнер для контента
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("НЕ ТЕСТИРОВАЛОСЬ")

                # Распорка снизу
                yield Static(id="bottom-spacer")
                
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next")
                
                yield Static(id="bottom-margin")
