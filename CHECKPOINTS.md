# Checkpoints (giảng viên đi bàn đối chiếu)

**M0 — Môi trường.** Thư mục `data/` có đủ 28 file A01…A16, B01…B12. `road_check selftest` in `SELFTEST PASS`. Đăng nhập được CVAT lớp và mở được `d11-road-<tên>`. Ai thiếu thì trợ giảng hỗ trợ ngay, lớp không dừng chờ.

**Task 0 — Project.** Có sáu label (lane, road_curb, crosswalk, drivable, traffic_light, traffic_sign) với đúng thuộc tính và giá trị. Có bốn label Tag (camera, timeofday, weather, source), mỗi label có thuộc tính select `value`. Bốn task: front, front-extra, fisheye, fisheye-extra.

**Task 1 — Ảnh đầu tiên (A01).** Coach kiểm ảnh đầu tiên của mỗi học viên:
- tag camera = front, đặt trước tiên;
- polyline vẽ từ gần ra xa;
- vạch đứt là một polyline;
- R1/L1 nằm trên tâm vạch;
- thuộc tính đã được sửa: CVAT tự điền giá trị đầu danh sách (polyline mới mang `L1 / solid / white / single`, tag `weather` mang `clear`). Vẽ xong mở Details sửa thuộc tính; đặt tag xong kiểm lại giá trị.

Gặp lỗi ở đây thì sửa ngay, đừng để lặp ra 11 ảnh sau.

**Task 1 — Giữa giờ (khoảng 14:20).** Đã xong khoảng 6 ảnh. A03 có occluded. A04 có vàng đôi (kind = double) và drivable chia direct/alternative. Box đèn ở A07–A08 sát vỏ và có màu đang sáng.

**Task 2 — Ảnh fisheye đầu tiên (B01).** Polyline đi theo cung, có nhiều điểm ở vòng ngoài. Tag camera đúng: FV → fisheye_front, RV → fisheye_rear, MVL → fisheye_left, MVR → fisheye_right. Thân xe mình không được gán.

**Task 2 — Camera hai bên (B05–B08).** Mọi lane có position = other. Vạch ngựa vạn được gán crosswalk (polygon), không gán lane.

**Task 3 — Phiếu QC 1.** Đủ 12 mã, mỗi mã có số mục đã kiểm. Mỗi lỗi ghi mã, ảnh, nhãn và mức. Tỉ lệ lỗi chính chia cho số nhãn đã kiểm, không chia cho số ảnh. Quyết định theo luật: còn lỗi nặng → Rework; tỉ lệ lỗi chính > 5 % → Rework; Hold chỉ khi còn ca mơ hồ mà lead chưa trả lời.

**Export.** Format là CVAT for images 1.1, không phải COCO. `road_check lint` không còn lỗi nặng; riêng QC1-02 (thiếu L1/R1) ở ảnh mà coach đã nhìn và xác nhận không thấy vạch thì được miễn; ghi mã ảnh và lý do vào phiếu QC 1. Tên file là `<tên>-front.zip` và `<tên>-fisheye.zip`. Job ở trạng thái completed. Đã tạo `<tên>-manifest.json` bằng `lint --manifest`, `contains_images` là `false`.

**Buffer.** Học viên sửa theo phiếu nhận được rồi export lại. Hoạt động row-anchor là tùy chọn, không chấm điểm.
