import os
from pathlib import Path
from typing import Optional

import aiofiles

from utils.custom_stealth.stealth_advanced import render_stealth_script

JS_BASE_DIR = Path(__file__).parent.parent / 'utils' / 'js_scripts'


async def load_js_script(
    file_name: str,
    *,
    user_agent: Optional[str] = None,
    browser_type: Optional[str] = None,
    is_mobile: Optional[bool] = None,
) -> str:
    """
    Load a JavaScript file content as string

    :param file_name: Name of the JavaScript file to load

    :return: The contents of the JavaScript file
    """

    normalized_file = file_name.replace('/', os.sep)

    if normalized_file in {
        "stealth_improved.js",
        "stealth_improved.obf.js",
        "all_in_one_steath.js",
    } and user_agent:
        platform_map = {
            "chrome": "chrome",
            "chromium": "chrome",
            "edge": "chrome",
            "firefox": "firefox",
            "webkit": "webkit",
        }
        platform = platform_map.get((browser_type or "").lower(), "chrome")
        return render_stealth_script(
            agent=user_agent,
            is_mobile=is_mobile,
            stealth_script=normalized_file,
            platform=platform,
        )

    file_path = JS_BASE_DIR / normalized_file

    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"JavaScript file not found: {file_path}")
