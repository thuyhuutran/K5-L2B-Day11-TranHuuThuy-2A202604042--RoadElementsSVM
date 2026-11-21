# Báo cáo cá nhân — Ngày 11

Họ tên: Trần Hữu Thủy (xác nhận lại dấu theo hồ sơ)  
Mã học viên và phiên bản CVAT: 2A202604042 - 2.81.0
Guideline: Road v1.0 · Revision: 1  
Thời điểm export ghi trong XML: fisheye 11:48:44, front 11:53:17 ngày 21/11/2026 (UTC+7).

## 1. Kiểm project

Trạng thái các job trên CVAT: **completed** (học viên xác nhận).

| Mục | Kết quả | Ghi chú |
| --- | --- | --- |
| 6 label, đúng kiểu | Khớp trong XML | Hai file khai báo đủ 6 label với kiểu tương ứng theo Road v1.0. |
| Thuộc tính và giá trị | Khớp trong danh mục XML | Đã đối chiếu danh mục trong XML với `configs/road_v1_labels.json`. |
| 4 tag ảnh | Đủ 28/28 ảnh | A01–A16 có camera đúng. B01–B12 đều đang dùng camera = front và cần sửa theo hậu tố tên ảnh. |

Trên CVAT, kết thúc polyline bằng cách nhấn lại nút Draw hoặc phím `N`. Đặt nhãn ảnh bằng công cụ Tag, chọn label rồi đặt thuộc tính `value`.

## 2. Số lượng đã gán

| Task | Ảnh | lane | road_curb | crosswalk | drivable | traffic_light | traffic_sign |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| front | 12 | 37 | 1 | 3 | 40 | 6 | 1 |
| front-extra (4/4 ảnh có shape) | 4 | 14 | 0 | 1 | 13 | 5 | 6 |
| fisheye | 8 | 11 | 2 | 10 | 10 | 5 | 2 |
| fisheye-extra (4/4 ảnh có shape) | 4 | 2 | 9 | 5 | 4 | 0 | 0 |

## 3. Bảng ca khó

| Ảnh | Nhãn | Phân vân giữa | Đã chọn | Lý do |
| --- | --- | --- | --- | --- |
| A05 | lane | Vạch bị mờ hay mặt đường không có vạch dọc | Giữ bản hiện tại, chờ coach xác nhận L1/R1 | Ảnh không cho thấy vạch dọc đủ rõ để xác định tim vạch. |
| A06 | lane | Vạch R1 hay phần mép đường trong bóng cầu | Chờ kiểm trực quan trên CVAT | Cần phân biệt vạch dọc với mép mặt đường trước khi bổ sung. |
| B06–B08 | camera | front hay camera bên | Theo tên ảnh: B06 dùng fisheye_left, B07–B08 dùng fisheye_right | XML đang ghi front. Hậu tố MVL/MVR xác định hướng camera. |

## 4. Phiếu QC 1 nhận được

Chờ tên người kiểm, phiếu nhận được và quyết định. Bảng dưới ghi kết quả tự kiểm bằng lint trên file bàn giao.

Lint trên hai ZIP hiện tại ghi nhận **40 cảnh báo** gồm **31 nặng** và **9 chính**.

| Mã | Mức | Số cảnh báo | Ghi chú |
| --- | --- | ---: | --- |
| QC1-01 | Nặng | 12 | B01–B12 đang có camera = front. |
| QC1-02 | Nặng | 19 | Lint báo thiếu L1/R1. Cần kiểm lại sau khi sửa tag camera của bộ B, vì tag front khiến lint áp quy tắc ảnh front. |
| QC1-04 | Chính | 5 | Kiểm chiều vẽ polyline gần đến xa. |
| QC1-05 | Chính | 4 | Kiểm các polyline trùng position và xem vạch đứt có bị tách không. |


## 5. Kiểm file export

| File | Mở lại được bằng lint | Số shape ảnh 1 (job / ZIP) | Số shape ảnh 2 (job / ZIP) | Tag camera có trong XML |
| --- | --- | ---: | ---: | --- |
| `tranhuuthuy-front.zip` | Có | A01: chưa đối chiếu / 9 | A02: chưa đối chiếu / 7 | Có, 16/16 |
| `tranhuuthuy-fisheye.zip` | Có | B01: chưa đối chiếu / 3 | B02: chưa đối chiếu / 5 | Có, 12/12, đều đang là `front` |

Cả hai ZIP chỉ có `annotations.xml`. Manifest ghi `contains_images: false` cho từng file.

Khi chạy từ thư mục gốc của repo, dùng đường dẫn tương đối có tiền tố `submission/`.

```bash
PYTHONPATH=src python -X utf8 -m road_lab.road_check lint submission/tranhuuthuy-front.zip submission/tranhuuthuy-fisheye.zip
```

Lần chạy chỉ truyền tên ZIP báo QC1-12 vì công cụ tìm file ở thư mục gốc. Khi dùng đường dẫn đầy đủ từ gốc repo, lint mở được cả hai ZIP và đọc 28 ảnh. Tổng 40 cảnh báo trong manifest là kết quả lần chạy đọc được cả hai file.

## 6. Ảnh chụp màn hình

Chờ bổ sung ảnh tab Labels, ảnh front đã gán, ảnh fisheye phóng to polyline và ảnh chụp XML. Đoạn XML thực tế để tìm nhanh trong file front tại A01:

```xml
<polyline label="lane" source="manual" occluded="0" points="616.86,652.97;520.70,585.64;481.23,558.25;463.50,544.50;452.00,536.00;442.34,529.67;434.04,523.89" z_order="0">
  <attribute name="position">R1</attribute>
  <attribute name="style">dashed</attribute>
  ...
</polyline>
```

## 7. Tự đánh giá

Trong bản export này, QC1-02 xuất hiện nhiều nhất. Nhiều cảnh báo ở bộ B phát sinh khi lint đọc camera = front. Ở Ngày 20 cần kiểm giá trị camera theo tên file, chạy lại lint và đối chiếu L1/R1 với ảnh trước khi xuất bản cuối.

Polyline làn được dùng để tạo đích huấn luyện cho nhận diện làn. Chẳng hạn, vị trí x của tim vạch tại các hàng neo được nội suy từ polyline. Nếu một vạch trên ảnh camera bên được ghi là L1 thay vì `other`, dữ liệu huấn luyện có sử dụng `position` sẽ gán nhầm vai trò của vạch đó.

## 8. Từ polyline đến đích row-anchor của A01

Chạy từ thư mục gốc của repo với polyline R1 trong ZIP front.

```bash
PYTHONPATH=src python -X utf8 -m road_lab.rowanchor submission/tranhuuthuy-front.zip --image A01
```

| y (px) | 720 | 680 | 640 | 600 | 560 |
| --- | ---: | ---: | ---: | ---: | ---: |
| x của tôi (px) | Không có làn | Không có làn | 598.3 | 541.2 | 483.8 |
| x của bạn được kiểm | Chưa có dữ liệu | Chưa có dữ liệu | Chưa có dữ liệu | Chưa có dữ liệu | Chưa có dữ liệu |

1. Nếu dừng đầu xa sớm 40 px theo trục y, đầu xa chuyển từ khoảng y=524 xuống y=564. Hàng y=560 đổi thành “không có làn”.
2. Cần kết quả của bạn được kiểm để so ở y=560. Ở y=720, vạch của tôi không giao hàng neo nên không có tọa độ x để tính độ lệch.
3. Đảo thứ tự điểm giữ nguyên các đoạn thẳng và giao điểm. Nội suy row-anchor cho cùng tọa độ x, còn `road_check lint` có thể báo QC1-04 nếu polyline được vẽ từ xa về gần.
