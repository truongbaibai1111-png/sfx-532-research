# SFX 532 Research — No API

Bộ công cụ nghiên cứu sound effect cho 532 video hoạt hình không lời, chạy local và không phụ thuộc Gemini/OpenAI/Freesound API.

## Production V0.1

Mục tiêu của V0.1 là xây nền dữ liệu đáng tin cậy trước khi gắn model AI local:

- Quét toàn bộ video cục bộ.
- Kiểm tra metadata bằng FFprobe.
- Tính SHA256 để phát hiện video bị thay đổi.
- Lưu trạng thái vào SQLite.
- Trích audio mono PCM16 16 kHz bằng FFmpeg.
- Phát hiện các đoạn âm thanh ứng viên bằng energy + onset/transient.
- Cắt từng audio event để kiểm tra.
- Resume: video đã xử lý không chạy lại nếu không cần.
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
Candidate detector
    ↓
Audio event clips + timestamp
    ↓
Review / research
    ↓
Cartoon SFX knowledge base
    ↓
Semantic search local (giai đoạn kế tiếp)
```

## Yêu cầu

- Windows 10/11 hoặc Linux
- Python 3.10+
- FFmpeg + FFprobe có trong PATH

## Cài đặt trên Windows

```bat
git clone https://github.com/truongbaibai1111-png/sfx-532-research.git
cd sfx-532-research
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Kiểm tra FFmpeg:

```bat
ffmpeg -version
ffprobe -version
```

## Cách chạy an toàn

Chép video vào:

```text
data/raw_videos/
```

Khởi tạo database:

```bat
python scripts/init_db.py
```

Quét video:

```bat
python scripts/scan_videos.py
```

Xem danh sách video ID:

```bat
python scripts/status.py
```

**Chỉ xử lý một video để kiểm thử trước:**

```bat
python scripts/process_video.py --video-id 1
```

Xuất CSV:

```bat
python scripts/export_csv.py
```

Không chạy `process_all.py` cho cả 532 video trước khi detector được kiểm thử và khóa phiên bản.

## Nguyên tắc dữ liệu

1. Video gốc là immutable: chương trình không sửa video gốc.
2. File được nhận diện bằng `relpath + SHA256`, không chỉ filename.
3. File thay đổi sẽ invalidate trạng thái derived tương ứng.
4. Detector chỉ tạo **candidate**, không tự kết luận candidate là SFX.
5. `HEARD_*` chỉ dùng cho âm thực sự có bằng chứng.
6. `CREATIVE_ONLY` dùng cho đề xuất sound design, không giả vờ đó là âm nghe được trong video.
7. Không đánh dấu `COMPLETE` khi stage bắt buộc chưa PASS.

## Trạng thái pipeline

```text
INGESTED
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

Nếu mất điện hoặc chương trình dừng giữa chừng, video hoàn tất trước đó vẫn giữ nguyên kết quả.

## Các giai đoạn tiếp theo

- V0.2: event package gồm video clip + frame trước/đỉnh/sau.
- V0.3: review UI local.
- V0.4: multilingual semantic search local.
- V0.5: audio embedding local.
- V1.0: truy vấn theo tình huống hoạt hình + SFX recipe + keyword tìm sound miễn phí.
