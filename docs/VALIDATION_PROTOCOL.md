# Detector Validation Protocol

Mục tiêu của bước này là khóa Detector V1 trước khi chạy 532 video. Không tối ưu dựa trên một cảm giác chung; phải đo bằng một video đại diện.

## 1. Chọn video kiểm thử

Chọn 1 video có đủ các loại tình huống sau nếu có thể:

- impact ngắn;
- scrape/rub liên tục;
- whoosh;
- bước chân/chuyển động cơ thể;
- nhạc nền;
- nhiều âm chồng nhau;
- đoạn yên tĩnh.

Không chọn video quá đơn giản chỉ để detector đạt điểm cao.

## 2. Chạy V0.1

```bat
python scripts/scan_videos.py
python scripts/status.py
python scripts/process_video.py --video-id 1
python scripts/export_csv.py
```

Các candidate được tạo tại:

```text
data/derived/events/video_0001/
```

Mỗi candidate gồm:

```text
event_XXXX.wav
event_XXXX.mp4
event_XXXX_before.jpg
event_XXXX_peak.jpg
event_XXXX_after.jpg
```

## 3. Review thủ công

Với từng candidate, đánh một trong bốn nhãn:

- TRUE_SFX: có SFX cần nghiên cứu.
- MUSIC_ONLY: detector chỉ bắt nhạc.
- AMBIENCE_ONLY: chỉ là nền/ambience.
- DUPLICATE_OR_FRAGMENT: cùng một hành động bị chia sai hoặc lặp.

Đồng thời ghi các SFX thật trong video mà detector bỏ sót.

## 4. Chỉ số khóa detector

Hai chỉ số quan trọng nhất:

```text
Recall = số SFX thật detector bắt được / tổng số SFX thật trong video
Precision candidate = TRUE_SFX / tổng candidate
```

Ở giai đoạn candidate detector, ưu tiên recall hơn precision vì candidate thừa còn có thể lọc; SFX bị bỏ sót thì mất dữ liệu nghiên cứu.

Mục tiêu ban đầu:

- Recall >= 95% với impact/transient rõ.
- Recall >= 90% tổng các cue đáng nghiên cứu.
- Không tạo lượng candidate lớn đến mức review không thực tế.
- Một cue không bị chia thành quá nhiều fragment nhỏ.

Các ngưỡng này là tiêu chí kỹ thuật nội bộ, không phải tuyên bố rằng detector đã nhận dạng được loại SFX.

## 5. Khi nào được chạy nhiều video hơn

Chỉ chuyển sang test 5–10 video khi:

1. Không còn lỗi crash trên video đầu tiên.
2. Timestamp candidate đúng.
3. WAV, MP4 và 3 frame được sinh đủ.
4. Chạy lại cùng video không tạo dữ liệu rác/stale.
5. Database và CSV khớp số candidate.
6. Detector không bỏ sót có hệ thống một nhóm cue quan trọng.

Sau test 5–10 video đa dạng mới freeze:

```text
pipeline_version
detector_version
schema_version
config thresholds
```

Sau khi freeze mới chạy 532 video.
