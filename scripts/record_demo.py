"""Запись демо-ролика работы KT Studio в docs/assets/demo.mp4.

Курсор и плавное ведение перенесены из ``ai_operations_agent/tools/record_demo.py``:
- реальные формы указателя macOS (``default``, ``pointer``, ``text``, ``grabbing``)
  переключаются по ``getComputedStyle(elementFromPoint(x, y)).cursor``;
- движение с кубическим ease-out и удержанием нажатия, человеческий набор текста
  и плавная прокрутка колесом.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

from playwright.sync_api import Locator, Page, sync_playwright  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parent.parent
CURSOR_DIR = ROOT / "docs" / "assets" / "cursor-shapes"
OUTPUT_MP4 = ROOT / "docs" / "assets" / "demo.mp4"
BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"

VIEWPORT = {"width": 1280, "height": 800}

SCROLL_STEP = 16
SCROLL_WAIT_MS = 24

CURSOR_SCALE = 0.30
CURSOR_SHAPES = {
    "default": ("default.png", 0.12, 0.08),
    "pointer": ("pointer.png", 0.35, 0.10),
    "text": ("text.png", 0.50, 0.50),
    "grabbing": ("grab.png", 0.50, 0.50),
}


@dataclass(frozen=True)
class Point:
    """Координаты указателя на экране."""

    x: float
    y: float


def cursor_assets() -> dict[str, dict[str, object]]:
    """Загружает вырезки форм курсора macOS в data URI."""
    assets: dict[str, dict[str, object]] = {}
    for name, (filename, hot_x, hot_y) in CURSOR_SHAPES.items():
        path = CURSOR_DIR / filename
        if not path.exists():
            raise SystemExit(f"Нет формы курсора {path}. Положите вырезки в docs/assets/cursor-shapes перед записью.")
        data = base64.b64encode(path.read_bytes()).decode()
        assets[name] = {
            "src": f"data:image/png;base64,{data}",
            "hotX": hot_x,
            "hotY": hot_y,
        }
    return assets


CURSOR_LAYER_JS = """
(assets) => {
  const SCALE = __SCALE__;
  const layer = document.createElement('div');
  layer.id = '__demo_cursor';
  Object.assign(layer.style, {
    position: 'fixed',
    left: '0px',
    top: '0px',
    zIndex: '2147483647',
    pointerEvents: 'none',
    willChange: 'transform',
    transform: 'translate(-1000px, -1000px)',
  });

  const images = {};
  for (const [name, info] of Object.entries(assets)) {
    const img = new Image();
    img.src = info.src;
    Object.assign(img.style, { position: 'absolute', display: 'none' });
    img.onload = () => {
      const w = img.naturalWidth * SCALE;
      const h = img.naturalHeight * SCALE;
      img.style.width = w + 'px';
      img.style.height = h + 'px';
      img.style.left = -(w * info.hotX) + 'px';
      img.style.top = -(h * info.hotY) + 'px';
    };
    images[name] = img;
    layer.append(img);
  }

  const show = (name) => {
    for (const [key, img] of Object.entries(images)) {
      img.style.display = key === name ? 'block' : 'none';
    }
  };
  show('default');

  const mount = () => {
    const root = document.documentElement;
    if (root && !layer.isConnected) root.append(layer);
  };
  mount();
  document.addEventListener('DOMContentLoaded', mount);

  window.__demoCursor = {
    shape: 'default',
    move(x, y) {
      mount();
      layer.style.transform = `translate(${x}px, ${y}px)`;
      const el = document.elementFromPoint(x, y);
      let shape = 'default';
      if (el) {
        const css = getComputedStyle(el).cursor;
        if (css === 'pointer') shape = 'pointer';
        else if (css === 'text') shape = 'text';
        else if (css === 'grab' || css === 'grabbing') shape = 'grabbing';
      }
      this.shape = shape;
      show(shape);
    },
  };

  document.addEventListener(
    'mousemove',
    (event) => window.__demoCursor.move(event.clientX, event.clientY),
    true,
  );
}
""".replace("__SCALE__", str(CURSOR_SCALE))


class Recorder:
    """Ведёт курсор, клавиатуру и прокрутку так, как это делает человек."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.pos = Point(VIEWPORT["width"] * 0.5, VIEWPORT["height"] * 0.5)

    def move_to(self, x: float, y: float, duration: float = 0.28) -> None:
        """Подводит курсор с кубическим замедлением у цели (ease-out)."""
        start = self.pos
        steps = max(5, int(duration / 0.022))
        for i in range(1, steps + 1):
            t = i / steps
            eased = 1 - math.pow(1 - t, 3)
            self.page.mouse.move(
                start.x + (x - start.x) * eased,
                start.y + (y - start.y) * eased,
            )
            self.page.wait_for_timeout(6)
        self.pos = Point(x, y)

    def pointer(self, x: float, y: float) -> None:
        """Коротким движением ставит указатель на исходную точку."""
        self.move_to(x, y, duration=0.18)

    def _wheel_by(
        self,
        delta: float,
        step: int = SCROLL_STEP,
        wait: int = SCROLL_WAIT_MS,
    ) -> None:
        """Прокручивает окно равномерными шагами колеса."""
        direction = 1 if delta > 0 else -1
        remaining = abs(delta)
        while remaining > 0.5:
            amount = min(step, remaining)
            self.page.mouse.wheel(0, direction * amount)
            self.page.wait_for_timeout(wait)
            remaining -= amount

    def scroll_to(
        self,
        locator: Locator,
        align: float = 0.5,
        tolerance: float = 24,
    ) -> None:
        """Плавно подводит элемент к нужной позиции в кадре при необходимости."""
        locator.wait_for(state="visible")
        self.page.wait_for_timeout(40)
        for _ in range(5):
            box = locator.bounding_box()
            if box is None:
                return
            if 40 <= box["y"] and box["y"] + box["height"] <= VIEWPORT["height"] - 40:
                return
            delta = box["y"] + box["height"] / 2 - VIEWPORT["height"] * align
            if abs(delta) <= tolerance:
                return
            info = self.page.evaluate(
                "() => ({y: window.scrollY,"
                " max: Math.max(0, document.documentElement.scrollHeight - window.innerHeight)})"
            )
            reach = min(max(info["y"] + delta, 0.0), info["max"]) - info["y"]
            if abs(reach) <= tolerance:
                return
            self._wheel_by(reach)
            self.page.wait_for_timeout(100)

    def hover(
        self,
        locator: Locator,
        duration: float = 0.28,
        settle: float = 0.18,
    ) -> Locator:
        """Плавно наводит курсор на элемент и выдерживает форму указателя."""
        self.scroll_to(locator)
        box = locator.bounding_box()
        if box is None:
            raise RuntimeError("Элемент не виден на странице")
        self.move_to(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, duration)
        self.pause(settle)
        return locator

    def click(
        self,
        locator: Locator,
        duration: float = 0.28,
        settle: float = 0.18,
        pause_after: float = 0.35,
    ) -> None:
        """Наводит курсор, выдерживает паузу, нажимает с естественным удержанием 70 мс."""
        self.hover(locator, duration, settle)
        self.page.mouse.down()
        self.page.wait_for_timeout(70)
        self.page.mouse.up()
        if pause_after > 0:
            self.pause(pause_after)

    def type_text(
        self,
        locator: Locator,
        text: str,
        delay: float = 40,
        pause_after: float = 0.35,
    ) -> None:
        """Ставит каретку кликом, выдерживает паузу и набирает текст посимвольно."""
        self.click(locator, settle=0.20, pause_after=0.0)
        self.page.wait_for_timeout(220)
        self.page.keyboard.press("ControlOrMeta+a")
        self.page.keyboard.type(text, delay=delay)
        if pause_after > 0:
            self.pause(pause_after)

    def pause(self, seconds: float) -> None:
        """Пауза для чтения результата действия."""
        self.page.wait_for_timeout(int(seconds * 1000))


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
    assets = cursor_assets()
    init_cursor_script = f"({CURSOR_LAYER_JS})({json.dumps(assets)});"

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
            context.add_init_script(init_cursor_script)
            page = context.new_page()
            rec = Recorder(page)

            # 1. Знакомство с темами (тайминги не меняем: 1.0s → 1.0s → 0.6s)
            page.goto(BASE_URL, wait_until="networkidle")
            page.get_by_text("API: ok · БД: ok").wait_for(timeout=15000)
            page.locator('button[type="submit"]:not(:disabled)').wait_for(timeout=20000)
            rec.pointer(640, 340)
            rec.pause(1.0)

            rec.click(page.locator('button[aria-label="Светлая тема"]'), pause_after=1.0)
            rec.click(page.locator('button[aria-label="Системная тема"]'), pause_after=0.6)

            # 2. Создание кампаний: имя, переключение Geo ES (по умолчанию) → AU, оффер
            rec.type_text(page.locator("#cmp-name"), "test_kulikov_demo_au", delay=40)
            rec.click(
                page.locator(".geo-chips button", has_text="AU"),
                settle=0.22,
                pause_after=0.5,
            )

            rec.type_text(page.locator("#cmp-offer"), "18001", delay=48, pause_after=0.45)
            first_offer = page.locator(".autocomplete-list .autocomplete-item").first
            first_offer.wait_for(timeout=10000)
            rec.click(first_offer, pause_after=0.6)

            rec.click(
                page.get_by_role("button", name="Create campaign"),
                settle=0.25,
                pause_after=0.2,
            )

            result_heading = page.locator(".result-card h2")
            result_heading.wait_for(timeout=25000)
            match = re.search(r"#(\d+)", result_heading.inner_text())
            if match:
                created_campaign_id = int(match.group(1))
            rec.pause(1.5)

            rec.click(
                page.get_by_role("button", name="Настроить кампанию"),
                settle=0.24,
                pause_after=0.5,
            )

            # 3. Редактор кампании: ждём загрузки потоков (Flow 1 + Flow 2)
            page.get_by_text("Stream: Офферы").wait_for(timeout=20000)
            rec.pause(1.2)

            # Добавляем 2 оффера (100% → 50/50 → 34/33/33) со спокойными паузами
            add_input = page.locator('input[aria-label="Поиск оффера для добавления в поток"]')
            add_btn = page.get_by_role("button", name="ADD", exact=True)
            for offer_code in ("18002", "18003"):
                rec.type_text(add_input, offer_code, delay=40, pause_after=0.3)
                item = page.locator(".autocomplete-list .autocomplete-item").first
                item.wait_for(timeout=5000)
                rec.click(item, settle=0.18, pause_after=0.25)
                rec.click(add_btn, settle=0.18, pause_after=0.8)

            # Ввод Share 25% + явный клик по Pin → пересчёт 38% / 37% / 25%
            share_inputs = page.locator("input.share-input:not(:disabled)")
            rec.type_text(share_inputs.nth(2), "25", delay=55, pause_after=0.55)
            rec.click(
                page.locator("button.pin-btn:not(:disabled)").nth(2),
                settle=0.22,
                pause_after=1.2,
            )

            # PUSH TO KT (38% / 37% / 25%) и пауза на результате
            rec.click(
                page.get_by_role("button", name="PUSH TO KT"),
                settle=0.25,
                pause_after=0.2,
            )
            page.get_by_text("Изменения сохранены в Keitaro").wait_for(timeout=20000)
            rec.pause(1.3)

            # REMOVE (0% / removed / BRING BACK) и откат через CANCEL
            rec.click(
                page.get_by_role("button", name="REMOVE", exact=True).nth(2),
                settle=0.20,
                pause_after=1.1,
            )
            rec.click(
                page.get_by_role("button", name="CANCEL", exact=True),
                settle=0.24,
                pause_after=1.0,
            )

            # 4. Переключение на вкладку Журнал операций
            rec.click(
                page.locator("nav.nav-tabs button", has_text="Журнал"),
                settle=0.24,
                pause_after=0.35,
            )
            page.locator(".data-table tbody tr").first.wait_for(timeout=10000)
            rec.pause(1.8)

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
