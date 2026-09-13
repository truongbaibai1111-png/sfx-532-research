# SFX 532 Research — No API

Bộ công cụ nghiên cứu sound effect cho 532 video hoạt hình không lời, chạy local và không phụ thuộc Gemini/OpenAI/Freesound API.

## Production V0.1

V0.1 xây nền dữ liệu và candidate extraction đủ bền để kiểm thử trên video thật trước khi gắn model AI local.

Đã có:

- Quét video cục bộ bằng FFprobe.
- SHA256 + size + mtime để nhận biết file thật sự thay đổi nhưng không hash lại 532 video mỗi lần chạy.
- Một file media lỗi không làm cả lượt scan dừng.
- SQLite có schema version + migration additive.
- Trích audio mono PCM16 16 kHz bằng FFmpeg.
- Candidate detector local: energy + onset + spectral flux, có noise-floor guard để đoạn im lặng không bị coi là event.
- Mỗi candidate sinh đủ:
  - WAV;
  - MP4 ngắn;
  - frame trước cue;
  - frame tại peak;
  - frame sau cue;
  - timestamp + score.
- Resume/checkpoint theo từng video.
- Dữ liệu đã review về sau được bảo vệ khỏi việc vô tình regenerate candidate.
- Tách dữ liệu nghe được khỏi đề xuất sound design sáng tạo.
- Xuất CSV để kiểm tra hoặc đưa cho ChatGPT nghiên cứu tiếp.

## Kiến trúc

```text
532 video gốc
    ↓
Ingest + SHA256 + FFprobe
    ↓
SQLite manifest
    ↓
FFmpeg audio extraction
    ↓
Energy + onset + spectral-flux detector
    ↓
Event package
(WAV + MP4 + 3 frames + timestamp)
    ↓
Review / research
    ↓
Cartoon SFX knowledge base
    ↓
Semantic search local (giai đoạn tiếp theo)
```

## Yêu cầu

- Windows 10/11 hoặc Linux
- Python 3.10+
- FFmpeg + FFprobe có trong PATH

## Cài đặt nhanh trên Windows

Clone repo:

```bat
git clone https://github.com/truongbaibai1111-png/sfx-532-research.git
cd sfx-532-research
```

Sau đó chạy:

```bat
setup_windows.bat
```

File này sẽ:

1. kiểm tra Python;
2. kiểm tra FFmpeg/FFprobe;
3. tạo `.venv`;
4. cài dependency;
5. tạo SQLite;
6. chạy self-test synthetic, gồm cả kiểm tra silence.

Nếu muốn cài thủ công:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\self_test.py
```

## Bước kiểm thử bắt buộc trước 532 video

Không chép cả 532 video vào để chạy batch ngay.

Đầu tiên chỉ chép **1 video đại diện** vào:

```text
data/raw_videos/
```

Sau đó:

```bat
.venv\Scripts\activate
python scripts\scan_videos.py
python scripts\status.py
python scripts\process_video.py --video-id 1
python scripts\export_csv.py
```

Candidate của video 1 nằm tại:

```text
data/derived/events/video_0001/
```

Mỗi candidate có dạng:

```text
event_0001.wav
event_0001.mp4
event_0001_before.jpg
event_0001_peak.jpg
event_0001_after.jpg
```

Quy trình đánh giá chi tiết nằm ở:

```text
docs/VALIDATION_PROTOCOL.md
```

Không chạy `scripts/process_all.py` cho 532 video trước khi detector đạt tiêu chí kiểm thử và được freeze version.

## Nguyên tắc dữ liệu

1. Video gốc là immutable: chương trình không sửa video gốc.
2. File được nhận diện bằng nội dung (SHA256), không chỉ filename.
3. Lượt scan sau dùng size + mtime fast-path; chỉ hash lại file có dấu hiệu thay đổi.
4. Nếu bytes video thay đổi, research derived từ bản cũ bị invalidate.
5. Detector chỉ tạo **candidate**, không tự kết luận candidate là SFX.
6. `HEARD_*` chỉ dùng cho âm thực sự có bằng chứng.
7. `CREATIVE_ONLY` dùng cho đề xuất sound design, không giả vờ đó là âm nghe được trong video.
8. Không đánh dấu `COMPLETE` khi stage bắt buộc chưa PASS.
9. Database có schema version để nâng cấp mà không xóa dữ liệu nghiên cứu.

## Trạng thái pipeline

```text
VALIDATED
  ↓
PENDING
  ↓
RUNNING
  ↓
CANDIDATES_READY
  ↓
RESEARCHED        (giai đoạn sau)
  ↓
INDEXED           (giai đoạn sau)
  ↓
COMPLETE          (giai đoạn sau)
```

File lỗi được đánh dấu `INVALID` và lượt scan tiếp tục với các file còn lại.

## Roadmap

- V0.1 — ingest, integrity, event packages, detector, SQLite, CSV: **đang kiểm thử trên video thật**.
- V0.2 — review UI local + đo precision/recall trên test set.
- V0.3 — visual-motion candidate detector để không phụ thuộc riêng audio.
- V0.4 — multilingual semantic search local.
- V0.5 — audio embedding local và hybrid reranking.
- V1.0 — nhập tình huống hoạt hình → trả reference trong 532 video + SFX recipe + keyword tìm sound miễn phí.
