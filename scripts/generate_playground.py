"""Generate synthetic, redistributable search fixtures. Labels are never in inbox/."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def font(size, bold=False):
    candidates = [ROOT / 'secondbrain/web/fonts/DM-Sans.ttf',
                  Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'),
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def product(path, color, price, title):
    image = Image.new('RGB', (1000, 740), '#f4f3ef')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1000, 70), fill='white')
    draw.text((40, 22), 'EVERYDAY GOODS', font=font(23, True), fill='#24392c')
    draw.text((745, 26), 'Footwear / Collection', font=font(17), fill='#60705c')
    draw.rounded_rectangle((35, 110, 965, 520), radius=12, fill='#e9e7df')
    # Simple geometric product illustration: synthetic fixture, not a real brand.
    draw.ellipse((190, 410, 840, 475), fill='#d6d3c8')
    draw.polygon([(206, 391), (250, 251), (345, 251), (384, 330), (565, 358), (722, 353), (823, 392), (850, 429), (206, 429)], fill=color, outline='#9a9c8e', width=3)
    draw.rounded_rectangle((198, 419, 858, 462), radius=15, fill='#fcfcf5', outline='#b9bbaa', width=3)
    draw.line((215, 445, 840, 445), fill='#bcc2af', width=3)
    for offset in range(4):
        draw.line((390 + offset * 37, 333 + offset * 6, 359 + offset * 37, 372 + offset * 4), fill='#b9bdaa', width=6)
    draw.polygon([(275, 285), (305, 285), (348, 388), (316, 388)], fill='#d8d9ca')
    draw.text((48, 553), title, font=font(36, True), fill='#24392c')
    draw.text((48, 608), 'Leather court sneaker / everyday comfort', font=font(22), fill='#68705f')
    draw.text((48, 660), f'INR {price}', font=font(30), fill='#24392c')
    draw.text((780, 660), 'SAVE FOR LATER', font=font(17), fill='#4e6642')
    image.save(path)


def receipt(path, shop, items, total, invoice):
    image = Image.new('RGB', (760, 900), '#e9e7df')
    draw = ImageDraw.Draw(image)
    draw.rectangle((115, 35, 645, 865), fill='#fffef8')
    draw.text((180, 100), shop, font=font(38, True), fill='#263d30')
    draw.text((180, 162), 'Bengaluru, India', font=font(21), fill='#5d6858')
    draw.text((165, 230), invoice, font=font(22), fill='#34412e')
    draw.line((165, 285, 600, 285), fill='#bdc2b4', width=2)
    y = 330
    for label, amount in items:
        draw.text((165, y), label, font=font(25), fill='#34412e')
        draw.text((520, y), str(amount), font=font(25), fill='#34412e')
        y += 75
    draw.line((165, y + 5, 600, y + 5), fill='#bdc2b4', width=2)
    draw.text((165, y + 46), 'TOTAL INR', font=font(27, True), fill='#24392c')
    draw.text((465, y + 46), str(total), font=font(32, True), fill='#24392c')
    draw.text((180, 785), 'Thank you. See you again.', font=font(20), fill='#65705d')
    image.save(path)


def screen(path, heading, lines, dark=False):
    image = Image.new('RGB', (1000, 740), '#222c30' if dark else '#eef0e7')
    draw = ImageDraw.Draw(image)
    fill = '#e4ebdf' if dark else '#2f4834'
    draw.text((55, 55), heading, font=font(37, True), fill=fill)
    y = 155
    for line in lines:
        draw.text((55, y), line, font=font(24), fill=fill)
        y += 73
    image.save(path)


def speech(path, text):
    if os.name == 'nt':
        def quoted(value): return "'" + str(value).replace("'", "''") + "'"
        script = ('Add-Type -AssemblyName System.Speech; '
                  '$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                  f'$voice.SetOutputToWaveFile({quoted(path)}); '
                  f'$voice.Speak({quoted(text)}); $voice.Dispose()')
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], check=True, capture_output=True)
    elif shutil.which('espeak'):
        subprocess.run(['espeak', '-w', str(path), text], check=True)
    else:
        print('No local speech synthesizer found; keep the shipped WAV fixtures or add your own voice memo.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'playground'))
    parser.add_argument('--no-audio', action='store_true')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    screenshots = root / 'inbox/screenshots'
    receipts = root / 'inbox/receipts'
    notes = root / 'inbox/notes'
    voice = root / 'inbox/voice'
    for folder in (screenshots, receipts, notes, voice): folder.mkdir(parents=True, exist_ok=True)
    product(screenshots / 'capture_001.png', '#fbfbf2', '2999', 'The white court sneaker')
    product(screenshots / 'capture_002.png', '#fbfbf2', '2499', 'The white court sneaker')
    product(screenshots / 'capture_003.png', '#7e9276', '3499', 'The forest green court sneaker')
    shutil.copyfile(screenshots / 'capture_001.png', screenshots / 'capture_001_copy.png')
    receipt(receipts / 'receipt_001.png', 'JUNIPER CAFE', [('Flat white', 180), ('Avocado toast', 320), ('Chocolate cake', 190)], 690, 'INV-2026-1042')
    receipt(receipts / 'receipt_002.png', 'THE BOOK NOOK', [('Design of Everyday', 640)], 640, 'BOOK-7718')
    screen(screenshots / 'capture_004.png', 'Database connection failed', ['ECONNREFUSED 127.0.0.1:5432', 'PostgreSQL server is not running.', 'Start the database service and retry.', 'Project: local second brain'], True)
    screen(screenshots / 'capture_005.png', 'A weekend in Jaipur', ['Saturday / Hawa Mahal at 9 AM', 'Lunch at the old city market', 'Sunday / Amber Fort at 10 AM', 'Remember: comfortable walking shoes'])
    (notes / 'note_001.md').write_text('# Launch meeting\nThe design review is scheduled for Friday at 3 PM. Priya owns the landing page. Arjun will prepare the database migration. Ship the search prototype before the review.\n', encoding='utf-8')
    (notes / 'note_002.txt').write_text('Weekend packing list: hiking backpack, rain jacket, water bottle, flashlight, and comfortable shoes. The camping stove is in the garage.\n', encoding='utf-8')
    if not args.no_audio:
        speech(voice / 'memo_001.wav', 'A note for later. The cafe we liked was called Juniper Cafe. It is near the old library. We should go back for their flat white and avocado toast next Saturday.')
        speech(voice / 'memo_002.wav', 'Remember the project meeting. Priya is handling the design review on Friday at three in the afternoon. Bring the new screenshots and the search prototype.')
    now = datetime.now().astimezone()
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=15, hour=14)
    for folder in (screenshots, receipts, notes, voice):
        for file in folder.iterdir():
            if file.is_file(): os.utime(file, (now.timestamp(), now.timestamp()))
    for name in ['capture_001.png', 'capture_001_copy.png', 'capture_002.png']:
        os.utime(screenshots / name, (last_month.timestamp(), last_month.timestamp()))
    scenarios = [
        {'id': 'visual-white-shoe', 'query': 'white sneakers', 'kind': 'image', 'expected_files': ['capture_001.png', 'capture_002.png']},
        {'id': 'relative-date', 'query': 'white sneaker last month', 'kind': 'image', 'expected_files': ['capture_001.png', 'capture_002.png']},
        {'id': 'changed-price', 'query': '2499', 'kind': 'image', 'expected_files': ['capture_002.png']},
        {'id': 'exact-receipt-number', 'query': 'INV-2026-1042', 'kind': 'image', 'expected_files': ['receipt_001.png']},
        {'id': 'cafe-receipt', 'query': 'Juniper cafe flat white', 'kind': 'image', 'expected_files': ['receipt_001.png']},
        {'id': 'developer-error', 'query': 'ECONNREFUSED PostgreSQL connection failed', 'expected_files': ['capture_004.png']},
        {'id': 'semantic-note', 'query': 'equipment to take camping', 'kind': 'text', 'expected_files': ['note_002.txt']},
        {'id': 'meeting-owner', 'query': 'Who is responsible for the design review?', 'kind': 'text', 'expected_files': ['note_001.md']},
        {'id': 'voice-cafe', 'query': 'cafe near the old library', 'kind': 'audio', 'expected_files': ['memo_001.wav']},
        {'id': 'voice-meeting', 'query': 'Friday design meeting', 'kind': 'audio', 'expected_files': ['memo_002.wav']},
        {'id': 'no-answer', 'query': 'my passport number on a submarine', 'kind': 'text', 'expected_files': []},
    ]
    (root / 'scenarios.json').write_text(json.dumps({'synthetic': True, 'generated_at': now.isoformat(), 'scenarios': scenarios}, indent=2), encoding='utf-8')
    print(f'Synthetic playground ready: {root}\nIndex only {root / "inbox"}; scenario labels are not evidence.')


if __name__ == '__main__': main()
