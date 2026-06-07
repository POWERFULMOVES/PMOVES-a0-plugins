#!/usr/bin/env python3
"""OpenRouter image generation script.
Usage: python generate_image.py <model> <prompt> <output_path>
Reads OPENROUTER_API_KEY from environment.
"""

import sys
import os
import json
import base64
import requests
from pathlib import Path

def generate_image(model: str, prompt: str, output_path: str):
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print('ERROR: OPENROUTER_API_KEY env var not set')
        sys.exit(1)

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    payload = {
        'model': model,
        'modalities': ['image', 'text'],
        'image_config': {
            'aspect_ratio': '1:1'
        },
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }

    print(f'Sending request to OpenRouter...')
    print(f'  Model:  {model}')
    print(f'  Prompt: {prompt}')
    print(f'  Output: {output_path}')

    resp = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers=headers,
        json=payload,
        timeout=120
    )

    if resp.status_code != 200:
        print(f'ERROR: HTTP {resp.status_code}')
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    print('Response received, parsing image...')

    # Find image in response content parts
    image_data = None
    image_ext = 'png'
    message = data.get('choices', [{}])[0].get('message', {})
    content = message.get('content', '')

    # Check message.images[] (used by some providers like Google via OpenRouter)
    for img in message.get('images', []):
        if isinstance(img, dict) and img.get('type') == 'image_url':
            url = img.get('image_url', {}).get('url', '')
            if url.startswith('data:image/'):
                fmt_b64 = url[len('data:image/'):]
                fmt, b64 = fmt_b64.split(';base64,', 1)
                image_ext = fmt
                image_data = b64
                break

    if not image_data and isinstance(content, str):
        if 'data:image' in content:
            parts = content.split('data:image/')
            for part in parts[1:]:
                fmt, b64 = part.split(';base64,', 1)
                image_ext = fmt.split('\n')[0].split('"')[0]
                image_data = b64.split('"')[0].split('<')[0].strip()
                break

    if not image_data and isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get('type') == 'image_url':
                    url = part.get('image_url', {}).get('url', '')
                    if url.startswith('data:image/'):
                        fmt_b64 = url[len('data:image/'):]
                        fmt, b64 = fmt_b64.split(';base64,', 1)
                        image_ext = fmt
                        image_data = b64
                        break
                elif part.get('type') == 'text':
                    text = part.get('text', '')
                    if 'data:image' in text:
                        idx = text.find('data:image/')
                        sub = text[idx:]
                        fmt_part = sub[len('data:image/'):]
                        fmt, b64 = fmt_part.split(';base64,', 1)
                        image_ext = fmt.split('"')[0].split('\n')[0]
                        image_data = b64.split('"')[0].split('<')[0].split()[0].strip()
                        break

    if not image_data:
        print('WARNING: No image found in response.')
        print(f'  finish_reason : {data.get("choices", [{}])[0].get("finish_reason")}')
        print(f'  message keys  : {list(message.keys())}')
        print(f'  content type  : {type(content).__name__}, len={len(str(content))}')
        sys.exit(1)

    # Determine output extension
    out = Path(output_path)
    if out.suffix == '':
        out = out.with_suffix(f'.{image_ext}')

    out.parent.mkdir(parents=True, exist_ok=True)
    img_bytes = base64.b64decode(image_data)
    out.write_bytes(img_bytes)
    print(f'Image saved: {out} ({len(img_bytes)} bytes)')


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python generate_image.py <model> <prompt> <output_path>')
        sys.exit(1)
    generate_image(sys.argv[1], sys.argv[2], sys.argv[3])
