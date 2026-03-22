from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Static
from rich.text import Text
from rich.console import RenderableType
from time import time
from asyncio import create_task, sleep

class AnimatedAsciiButtons(Widget):
    """Анимированные ASCII кнопки"""
    
    def __init__(self):
        super().__init__()
        self.pressed = False
        self.last_toggle = 0
        self.animation_task = None
    
    def on_mount(self):
        """Запускаем анимацию при монтировании"""
        self.animation_task = create_task(self.animate_buttons())
    
    async def animate_buttons(self):
        """Анимация кнопок каждые 2 секунды"""
        while True:
            # Ждем 2 секунды
            await sleep(2)
            # Включаем анимацию нажатия
            self.pressed = True
            self.refresh()
            # Ждем 1 секунду
            await sleep(1)
            # Выключаем анимацию
            self.pressed = False
            self.refresh()
    
    def render(self) -> RenderableType:
        if not self.pressed:
            # Состояние "нажато" - кнопки выглядят активными
            return Text(
                """
╭──────────────╮   ╭─────╮
│    Control   │ + │  Q  │    
╰──────────────╯   ╰─────╯      для выхода из приложения
 \\▁▁▁▁▁▁▁▁▁▁▁▁▁▁\\   \\▁▁▁▁▁\\

╭─────╮  ╭─────╮
│  <  │  │  >  │              
╰─────╯  ╰─────╯                с помощью этих клавиш вы можете листать quickstart guide
 \\▁▁▁▁▁\\  \\▁▁▁▁▁\\
"""
            )
        else:
            # Состояние "ненажато" - кнопки выглядят обычными
            return Text(
                """

╭──────────────╮   ╭─────╮
│    Control   │ + │  Q  │      для выхода из приложения
╰──────────────╯   ╰─────╯
 ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔    ▔▔▔▔▔▔

╭─────╮  ╭─────╮
│  <  │  │  >  │                с помощью этих клавиш вы можете листать quickstart guide
╰─────╯  ╰─────╯
 ▔▔▔▔▔▔   ▔▔▔▔▔▔
"""
            )

class LargeHello(Widget):
    """Отображение приветствия большим текстом."""
    
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
    
    def render(self) -> RenderableType:
        # Создаем большой текст с помощью Rich
        return Text(self._text, style="bold", justify="center")

class WelcomePage(Widget):
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
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-layout"):
            with Vertical(id="welcome-stack"):
                yield Static("", id="welcome-index")
                
                # Распорка сверху
                yield Static(id="top-spacer")
                
                # Скроллируемый контейнер для контента
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("NEOSAM")
                        yield Static("Добро пожаловать в простой устойчивый к блокировкам мессенджер на протоколе i2p!", classes="additional-widget")
                        # Добавляем анимированные ASCII кнопки
                        yield AnimatedAsciiButtons()

                # Распорка снизу
                yield Static(id="bottom-spacer")
                
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next")
                
                yield Static(id="bottom-margin")
    
    def on_unmount(self):
        """Останавливаем анимацию при закрытии"""
        pass