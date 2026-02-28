from engines.base import BrowserEngine


async def check_cloudflare_bypass(engine: BrowserEngine) -> bool:
    """
    Check if the cloudflare bypass is successful

    :param engine: BrowserEngine instance
    """

    element_found1, _ = await engine.locator('[title="Just a moment..."]')

    # for non-english challenge page
    element_found2, _ = await engine.locator('.main-content .core-msg.spacer.spacer-top')
    element_found3, _ = await engine.locator('input[name="cf-turnstile-response"]')
    element_found4, _ = await engine.locator(".main-content h2.ch-title")

    page_content = (await engine.get_page_content()).lower()
    blocked_markers = (
        "just a moment",
        "checking your browser",
        "checking if the site connection is secure",
        "enable javascript and cookies to continue",
        "выполнение проверки безопасности",
        "этот веб-сайт использует службу безопасности",
        "проверяет, что вы не бот",
        "cf-turnstile-response",
    )

    marker_found = any(marker in page_content for marker in blocked_markers)
    return not (element_found1 or element_found2 or element_found3 or element_found4 or marker_found)
