# SFX 532 Research — No API

Bộ công cụ nghiên cứu sound effect cho 532 video hoạt hình không lời, chạy local và không phụ thuộc Gemini/OpenAI/Freesound API.

## Detector V0.2

V0.2 được xây sau khi audit thủ công 24 mẫu của video 001. Mục tiêu là giữ recall cao nhưng giảm over-segmentation và không tạo hàng trăm file media nặng cho mọi transient.

Điểm mới:

- Energy + onset + spectral flux vẫn là ba nguồn tín hiệu chính.
- Sustained high energy không còn tự giữ một event active nếu không có thay đổi cục bộ.
- Tăng merge gap và thêm clustering/NMS giữa các fragment gần nhau.
- Tính spectral flatness để down-rank cue quá tonal thay vì xóa cứng.
- Chia candidate thành hai tầng:
  - `PRIMARY`: review-ready, sinh WAV + MP4 + 3 frame.
  - `SECONDARY`: vẫn lưu timestamp/features trong SQLite nhưng không sinh file media nặng.
- Candidate ở vài giây cuối video được hạ xuống SECONDARY để giảm title/end-card sting; dữ liệu không bị xóa.
- SQLite schema 3 thêm `review_score`, `review_tier`, `trigger_count`, `spectral_flatness`, `tonal_penalty`.
- Pipeline tự migrate database cũ theo kiểu additive.
- `candidate_report.py` báo riêng ALL / PRIMARY / SECONDARY và union coverage.

## Kiến trúc hiện tại

```text
532 video gốc
    ↓
Ingest + SHA256 + FFprobe
    ↓
SQLite manifest
    ↓
FFmpeg audio extraction
    ↓
Detector V0.2
energy + onset + spectral flux
    ↓
merge + clustering + soft tonal ranking
    ↓
ALL RETAINED CANDIDATES
    ├── PRIMARY → WAV + MP4 + 3 frames → review trước
    └── SECONDARY → metadata only → giữ để phục hồi recall
    ↓
Research / labeling
    ↓
Cartoon SFX knowledge base
```

## Yêu cầu

- Windows 10/11 hoặc Linux
- Python 3.11 được khuyến nghị
- FFmpeg + FFprobe trong PATH

## Cài đặt Windows

```bat
setup_windows.bat
```

Setup sẽ chọn Python 3.11 nếu có, tạo `.venv`, cài dependency và chạy self-test.

## Kiểm thử video 001 sau khi nâng V0.2

Không chạy 532 video ngay.

Giữ video 001 trong:

```text
data/raw_videos/
```

Chạy:

```bat
.venv\Scripts\activate
python scripts\process_video.py --video-id 1
python scripts\status.py
python scripts\candidate_report.py --video-id 1
```

`process_video.py` được phép regenerate khi video đang ở trạng thái `CANDIDATES_READY`. Nó sẽ xóa event package cũ của video đó và tạo lại theo V0.2. Các trạng thái `RESEARCHED`, `INDEXED`, `COMPLETE` vẫn được bảo vệ khỏi regenerate ngoài ý muốn.

Kết quả V0.2 cần được đánh giá theo:

- số ALL candidates;
- số PRIMARY;
- số SECONDARY;
- PRIMARY/minute;
- union coverage;
- số candidate được cluster từ nhiều trigger;
- precision/recall của một audit sample mới.

Không đặt mục tiêu máy móc rằng tổng candidate phải xuống một con số cố định. Mục tiêu là PRIMARY sạch hơn trong khi SECONDARY vẫn giữ các cue yếu.

## Nguyên tắc dữ liệu

1. Video gốc là immutable.
2. File được nhận diện bằng SHA256 + size + mtime.
3. Video thay đổi bytes sẽ invalidate dữ liệu derived cũ.
4. Detector chỉ tạo candidate, không tự kết luận đó chắc chắn là SFX.
5. `PRIMARY`/`SECONDARY` chỉ là thứ tự review, không phải nhãn true/false.
6. `HEARD_*` chỉ dành cho âm có bằng chứng thật.
7. `CREATIVE_ONLY` là đề xuất sound design, không được trộn với âm nghe được.
8. Không đánh dấu `COMPLETE` khi stage bắt buộc chưa PASS.
9. Migration database phải additive, không xóa research đã có.

## Roadmap

- V0.1 — ingest, integrity, detector high-recall ban đầu: hoàn thành.
- V0.2 — clustering + review tier + giảm file spam: **đang kiểm thử trên video 001**.
- V0.3 — visual-motion/context reranking local.
- V0.4 — multilingual semantic search local.
- V0.5 — audio embedding local + hybrid reranking.
- V1.0 — nhập tình huống hoạt hình → reference trong 532 video + SFX recipe + keyword tìm sound miễn phí.
