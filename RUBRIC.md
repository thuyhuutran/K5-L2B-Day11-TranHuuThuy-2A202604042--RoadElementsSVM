# Rubric — Ngày 11 · Road Elements & SVM

Nguồn: hướng dẫn lab coach Ngày 11, Phần 8 "Cách chấm điểm". Bảng dưới **giống hệt** bảng trong [`lab/AGENTS.md`](lab/AGENTS.md), kể cả điểm thưởng; `tests/test_checker.py` kiểm hai bảng trùng nhau từng ký tự.

<!-- rubric:start -->
| Tiêu chí | Cách đo | Điểm |
| --- | --- | ---: |
| Project, tag và file | Mọi ảnh đủ bốn tag, camera đúng (4); export CVAT for images 1.1 mở lại được, đúng tên label và thuộc tính (4); ảnh chụp và bảng kiểm file (2) | 10 |
| Polyline làn, Set A | Đủ L1/R1 trên mọi ảnh thấy được (8); khoảng cách lớn nhất tới GT ≤ 5 px theo `road_check.py` (9); chiều gần ra xa, vạch đứt một polyline, nối qua chỗ che có `occluded`, dừng đúng chỗ (8) | 25 |
| Thuộc tính làn | Tỉ lệ khớp GT của `position` (5), `style` / `color` / `kind` (5) | 10 |
| Vùng lái được | Không tràn lề, vỉa hè, thân xe, phần sau cọc (6); `direct` / `alternative` đúng (4) | 10 |
| Đèn và biển | Đủ đèn, biển từ 8 px, không gán hình in (5); box sát vỏ, mép biển (4); `color`, `facing`, `type`, `group`, biển phụ riêng (6) | 15 |
| Fisheye, Set B | Polyline theo cung, lệch ≤ 5 px (5); thân xe không gán, `position = other` ở camera hai bên, `edge_zone` đúng (5) | 10 |
| Phiếu QC 1 cho bạn khác | Đủ 12 mã có số mục kiểm (3); mỗi lỗi có mã, ảnh, nhãn, mức (5); tỉ lệ tính trên số nhãn kiểm và quyết định đúng luật (4); coach kiểm lại 3 lỗi được ghi và 1 ảnh được ghi "không lỗi": khớp (3) | 15 |
| Báo cáo cá nhân | Bảng ca khó có lý do (2), mục 4 phản hồi phiếu nhận được (2), tự đánh giá nối lỗi với model (1) | 5 |

**Tổng: 100.** Phần `road_check.py` chấm tự động: 78 điểm (mọi dòng trừ ảnh chụp 2, Phiếu QC 1 15, báo cáo 5 — coach chấm tay 22 điểm).

**Điểm thưởng ảnh thêm** (4 ảnh front A13–A16 + 4 ảnh fisheye B09–B12, tối đa +4, tổng không quá 100): mỗi ảnh thêm đạt — đủ bốn tag, đủ label ghi ở bảng kế hoạch, lệch polyline ≤ 5 px trên 2 vạch kiểm ngẫu nhiên, không lỗi nặng — được +0,5 điểm. Coach kiểm tay vì ảnh thêm không có GT đầy đủ. Ảnh thêm bỏ qua không bị trừ điểm.

**Ảnh bắt buộc chưa làm** chỉ làm giảm số ảnh được chấm: các tiêu chí tính theo tỉ lệ trên số ảnh đã làm. Làm ít mà đúng được điểm hơn làm nhiều mà ẩu.

**Đạt:** ≥ 60 điểm **và** lô của chính học viên không còn lỗi nặng sau buffer theo Phiếu QC 1 (tag camera đúng mọi ảnh, đủ L1/R1, không đổi nhầm `position`, không sai màu đèn quay về xe, file mở lại được).

Hoạt động buffer và mục 8 của báo cáo không tính điểm.
<!-- rubric:end -->

## Dòng rubric ↔ phần tự động của `road_check.py`

| Dòng rubric | Id trong `RUBRIC` | Điểm | Mã QC1 làm trừ điểm |
| --- | --- | ---: | --- |
| Project, tag và file | `tags` 4 · `file` 4 · `screens` 2 (tay) | 10 | QC1-01, QC1-12 |
| Polyline làn, Set A | `l1r1` 8 · `dev` 9 · `dir` 8 | 25 | QC1-02, QC1-04, QC1-05 |
| Thuộc tính làn | `pos` 5 · `sck` 5 | 10 | QC1-03, QC1-06 |
| Vùng lái được | `spill` 6 · `atype` 4 | 10 | QC1-07 |
| Đèn và biển | `presence` 5 · `tight` 4 · `battr` 6 | 15 | QC1-08, QC1-09, QC1-10 |
| Fisheye, Set B | `arc` 5 · `ferule` 5 | 10 | QC1-11, QC1-03 (camera hai bên) |
| Phiếu QC 1 cho bạn khác | `qc1` (tay) | 15 | — |
| Báo cáo cá nhân | `report` (tay) | 5 | — |

Ngưỡng của checker (`THRESHOLDS` trong `src/road_lab/road_check.py`) và trạng thái của từng ngưỡng: xem [`lab/AGENTS.md`](lab/AGENTS.md) mục 4. Ngưỡng 5 px, 8 px, 80 % bán kính và 5 % lỗi chính lấy từ guideline; các ngưỡng ghép cặp (25 px, 15 px, IoU) là **quyết định thiết kế của Lab Coach**, chưa hiệu chỉnh trên bài thật.
