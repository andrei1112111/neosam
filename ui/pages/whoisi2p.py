from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Static
from rich.text import Text
from rich.console import RenderableType
from time import time
from asyncio import create_task, sleep


class LargeHello(Widget):
    """Отображение приветствия большим текстом."""
    
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
    
    def render(self) -> RenderableType:
        # Создаем большой текст с помощью Rich
        return Text(self._text, style="bold", justify="center")

class WhoIsI2P(Widget):
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

    #welcome-top-row {
        width: 100%;
        height: auto;
    }

    #welcome-index {
        width: 1fr;
        content-align: left top;
        text-style: bold;
        margin: 1 0 0 1;
    }

    #close-app {
        width: auto;
        border: none;
        background: transparent;
        text-style: bold;
        margin: 1 1 0 0;
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
                with Horizontal(id="welcome-top-row"):
                    yield Static("i2p", id="welcome-index")
                    yield Button("[ закрыть ]", id="close-app")
                
                # Распорка сверху
                yield Static(id="top-spacer")
                
                # Скроллируемый контейнер для контента
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("Что такое i2p и зачем он вам. (работает при белых списках и в обход ТСПУ)")
                        yield Static('I2P - это секретная сеть внутри обычного интернета, где никто не может узнать кто вы и чем занимаетесь. Представьте, что каждое ваше сообщение проходит через несколько случайных узлов которые передают его дальше и ни один из них не знает ни отправителя, ни получателя. Это позволяет общаться, смотреть сайты и обмениваться файлами полностью анонимно.', classes="additional-widget")
                    with Container(classes="content-container"):
                        yield Static('I2P работает независимо от государственных блокировок и цензуры. Даже если провайдер закрыл доступ к обычным сайтам, внутри I2P вы все равно сможете заходить на любые ресурсы, потому что трафик запутанно шифруется и передается через сеть добровольцев по всему миру, которую невозможно заблокировать точечно. Проще говоря, это способ оставаться на связи, получать информацию и общаться свободно, когда обычный интернет ограничен или недоступен.', classes="additional-widget")

                # Распорка снизу
                yield Static(id="bottom-spacer")
                
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next")
                
                yield Static(id="bottom-margin")
    
