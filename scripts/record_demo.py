"""Запись демо-скриншота/видео работы Keitaro Campaign Manager в docs/assets/demo.mp4.

Сценарий проигрывает живой пользовательский поток в браузере (1280x800):
1. Переключение тем (тёмная → светлая → системная) как в эталоне ai_operations_agent.
2. Создаватор кампаний: имя, гео, автокомплит оффера, создание кампании с 2 потоками.
3. Редактор кампании: ADD, PUSH TO KT, REMOVE (0% / removed), SHOW ALL OFFERS,
   BRING BACK, Pin / ручная доля Share (25% + 38% + 37%), CANCEL, FETCH STREAMS FROM KT.
4. Журнал операций в PostgreSQL.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_MP4 = ROOT / "docs" / "assets" / "demo.mp4"
BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"

VIEWPORT = {"width": 1280, "height": 800}

# Векторный курсор поверх страницы (страница пишется без системного курсора ОС)
CURSOR_INIT_JS = """
(() => {
  const initCursor = () => {
    if (document.getElementById('__demo_cursor')) return;
    const el = document.createElement('div');
    el.id = '__demo_cursor';
    Object.assign(el.style, {
      position: 'fixed',
      left: '0px',
      top: '0px',
      width: '20px',
      height: '20px',
      zIndex: '2147483647',
      pointerEvents: 'none',
      transform: 'translate(-100px, -100px)',
      transition: 'transform 0.03s linear',
      filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.45))',
    });
    el.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none">
      <path d="M4 3l14 7.2-6.2 1.8L9.6 18.5 4 3z" fill="#ffffff" stroke="#111317" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>`;
    document.body.appendChild(el);
    window.addEventListener('mousemove', (e) => {
      el.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    }, { passive: true });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCursor);
  } else {
    initCursor();
  }
})();
"""


def move_and_click(page: Page, locator: Locator, pause_after: float = 0.25) -> None:
    """Плавно подводит курсор к элементу, нажимает на него и делает короткую паузу."""
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box is None:
        locator.click()
    else:
        target_x = box["x"] + box["width"] / 2
        target_y = box["y"] + box["height"] / 2
        page.mouse.move(target_x, target_y, steps=12)
        time.sleep(0.12)
        page.mouse.click(target_x, target_y)
    if pause_after > 0:
        time.sleep(pause_after)


def type_human(page: Page, locator: Locator, text: str, delay_ms: int = 35) -> None:
    """Кликает по полю, очищает его и вводит текст с живой скоростью."""
    move_and_click(page, locator, pause_after=0.1)
    locator.fill("")
    locator.press_sequentially(text, delay=delay_ms)
    time.sleep(0.2)


def cleanup_campaign(campaign_id: int) -> None:
    """Удаляет демонстрационную кампанию из Keitaro после завершения записи."""
    req = urllib.request.Request(
        f"{API_URL}/api/campaigns/{campaign_id}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Cleanup DELETE /api/campaigns/{campaign_id}: {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"Cleanup warning for #{campaign_id}: HTTP {exc.code}")


def convert_webm_to_mp4(webm_path: Path, mp4_path: Path) -> None:
    """Конвертирует запись Playwright WebM в MP4 (H.264, yuv420p, faststart)."""
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(webm_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-movflags",
        "+faststart",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main() -> None:
    """Выполняет сценарий записи демо-ролика и сохраняет его в docs/assets/demo.mp4."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="kcm-demo-"))
    created_campaign_id: int | None = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport=VIEWPORT,
                color_scheme="dark",
                record_video_dir=str(tmp_dir),
                record_video_size=VIEWPORT,
            )
            context.add_init_script(CURSOR_INIT_JS)
            page = context.new_page()

            # 1. Загрузка интерфейса и знакомство с переключателем тем
            page.goto(BASE_URL, wait_until="networkidle")
            page.get_by_text("API: ok · БД: ok").wait_for(timeout=15000)
            # Ждём, пока кнопка Create campaign станет активной (справочники загружены)
            page.locator('button[type="submit"]:not(:disabled)').wait_for(timeout=20000)
            page.mouse.move(640, 360, steps=8)
            time.sleep(1.0)

            move_and_click(
                page,
                page.locator('button[aria-label="Светлая тема"]'),
                pause_after=1.0,
            )
            move_and_click(
                page,
                page.locator('button[aria-label="Системная тема"]'),
                pause_after=0.6,
            )

            # 2. Создаватор кампаний
            type_human(page, page.locator("#cmp-name"), "Demo AU Campaign")
            move_and_click(
                page,
                page.locator(".geo-chips button", has_text="AU"),
                pause_after=0.25,
            )

            offer_input = page.locator("#cmp-offer")
            type_human(page, offer_input, "18001", delay_ms=55)
            page.locator(".autocomplete-list .autocomplete-item").first.wait_for(timeout=10000)
            move_and_click(
                page,
                page.locator(".autocomplete-list .autocomplete-item").first,
                pause_after=0.35,
            )

            create_btn = page.get_by_role("button", name="Create campaign")
            move_and_click(page, create_btn, pause_after=0.2)

            result_heading = page.locator(".result-card h2")
            result_heading.wait_for(timeout=25000)
            heading_text = result_heading.inner_text()
            match = re.search(r"#(\d+)", heading_text)
            if match:
                created_campaign_id = int(match.group(1))
            time.sleep(1.1)

            move_and_click(
                page,
                page.get_by_role("button", name="Открыть в редакторе"),
                pause_after=0.4,
            )

            # 3. Редактор кампании: ждём загрузки потоков
            page.get_by_text("Stream: Офферы").wait_for(timeout=20000)
            time.sleep(0.8)

            # Добавляем 4 оффера (в итоге 5 активных по 20%)
            add_input = page.locator('input[aria-label="Поиск оффера для добавления в поток"]')
            add_btn = page.get_by_role("button", name="ADD", exact=True)
            for offer_code in ("18002", "18003", "18004", "18005"):
                type_human(page, add_input, offer_code, delay_ms=45)
                page.locator(".autocomplete-list .autocomplete-item").first.wait_for(timeout=5000)
                move_and_click(
                    page,
                    page.locator(".autocomplete-list .autocomplete-item").first,
                    pause_after=0.15,
                )
                move_and_click(page, add_btn, pause_after=0.35)

            time.sleep(0.7)

            # Отправляем 5 офферов (20% каждый) в Keitaro
            push_btn = page.get_by_role("button", name="PUSH TO KT")
            move_and_click(page, push_btn, pause_after=0.2)
            page.get_by_text("Изменения сохранены в Keitaro").wait_for(timeout=20000)
            time.sleep(0.8)

            # Удаляем два оффера → 34% / 33% / 33%, удалённые 0% + (removed) + BRING BACK
            remove_buttons = page.get_by_role("button", name="REMOVE", exact=True)
            move_and_click(page, remove_buttons.nth(4), pause_after=0.4)
            move_and_click(page, remove_buttons.nth(3), pause_after=0.7)

            # Проверяем переключатель SHOW ALL OFFERS (скрыть и снова показать удалённые)
            show_all_label = page.locator("label.checkbox-pill")
            move_and_click(page, show_all_label, pause_after=0.6)
            move_and_click(page, show_all_label, pause_after=0.6)

            # Восстанавливаем через BRING BACK и снова убираем для сценария Pin 25%
            bring_back_btns = page.get_by_role("button", name="BRING BACK", exact=True)
            move_and_click(page, bring_back_btns.first, pause_after=0.6)
            move_and_click(
                page.page if False else page,
                page.get_by_role("button", name="REMOVE", exact=True).nth(3),
                pause_after=0.6,
            )

            # Закрепляем долю 3-го активного оффера на 25% → первые два становятся 38% и 37%
            share_inputs = page.locator("input.share-input:not(:disabled)")
            type_human(page, share_inputs.nth(2), "25", delay_ms=60)
            time.sleep(0.8)

            # Пушим 38% / 37% / 25% в Keitaro
            move_and_click(page, page.get_by_role("button", name="PUSH TO KT"), pause_after=0.2)
            page.get_by_text("Изменения сохранены в Keitaro").wait_for(timeout=20000)
            time.sleep(0.8)

            # Демонстрация CANCEL (откат черновика) и FETCH STREAMS FROM KT
            move_and_click(
                page,
                page.get_by_role("button", name="REMOVE", exact=True).nth(2),
                pause_after=0.5,
            )
            move_and_click(
                page,
                page.get_by_role("button", name="CANCEL", exact=True),
                pause_after=0.6,
            )
            move_and_click(
                page,
                page.get_by_role("button", name="FETCH STREAMS FROM KT"),
                pause_after=0.9,
            )

            # 4. Переходим в Журнал операций
            move_and_click(
                page,
                page.locator("nav.nav-tabs button", has_text="Журнал"),
                pause_after=0.4,
            )
            page.locator(".data-table tbody tr").first.wait_for(timeout=10000)
            time.sleep(1.4)

            video = page.video
            context.close()
            browser.close()
            assert video is not None
            webm_path = Path(video.path())

        convert_webm_to_mp4(webm_path, OUTPUT_MP4)
        print(f"Saved screencast to {OUTPUT_MP4} ({OUTPUT_MP4.stat().st_size} bytes)")
    finally:
        if created_campaign_id is not None:
            cleanup_campaign(created_campaign_id)
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
