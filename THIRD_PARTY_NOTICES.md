# Third-party notices

`buddha/benchmark.py` reuses the exact `JUDGE_SYSTEM` and `SCORE_SYSTEM` strings
from NoveltyBench, and implements compatible rendering and ordering behavior.
The reference request fixture also preserves those exact prompt strings.
Source: https://github.com/novelty-bench/novelty-bench at commit
`64a23be6b18ec1dacc298830aab276061b6e143c`, `src/partition.py`, `src/score.py`,
`src/common.py`, and `src/judge.py`.

The upstream license follows in full.

MIT License

Copyright (c) 2025 Yiming Zhang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
