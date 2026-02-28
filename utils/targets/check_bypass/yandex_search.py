from engines.base import BrowserEngine


async def check_yandex_search_bypass(engine: BrowserEngine) -> bool:
    """
    Check if Yandex Search page is accessible and search input is present.

    :param engine: BrowserEngine instance
    """

    element_found, element_html = await engine.locator("input[name='text'], input[aria-label='Запрос']")

    return element_found
