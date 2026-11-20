# Thang mức lỗi QC 1 · Road v1.0

Thang này do khóa học xây dựng cho bài lab Ngày 11. Doanh nghiệp không công bố thang mức lỗi gán nhãn của họ, nên khóa học dựng thang dựa trên cách phân lớp lỗi của chuẩn quốc tế. Đây không phải thang của VinFast hay của dự án nào. Lab cũng không tuyên bố tuân thủ ISO 2859-1 hay ISO/IEC 5259.

Phiên bản: Road v1.0 · Áp dụng cho: Phiếu QC 1 và `road_check` · Không thay đổi: luật quyết định và ngưỡng 5 % trong bài.

## 1. Ba mức và tiêu chí xếp mức

Hỏi một câu cho mỗi lỗi: **nếu nhãn sai này đi vào dữ liệu huấn luyện, hậu quả là gì?**

| Mức | Tiêu chí | Hệ quả trên lô | Ví dụ trong lab |
| --- | --- | --- | --- |
| **nặng** | Làm sai ý nghĩa an toàn của cảnh, đưa cả ảnh vào sai nhóm dữ liệu, hoặc làm file không dùng được | Một lỗi là đủ để Rework | Tag camera sai; thiếu L1/R1 khi thấy được; nhầm làn của mình với làn bên cạnh; đèn đỏ gán xanh trên đèn hướng về xe; file không mở được hoặc thiếu một file zip |
| **chính** | Nhãn vẫn đúng đối tượng nhưng sai hình hoặc thuộc tính, mô hình học lệch | Rework khi tỉ lệ vượt 5 % số nhãn đã kiểm | Polyline lệch tâm vạch quá 5 px, ngược chiều, dừng sớm; vạch đứt bị tách; sai style/color; vùng lái tràn lề; box không sát; sai facing hoặc group; thiếu biển; fisheye không theo cung |
| **nhẹ** | Không đổi ý nghĩa của nhãn, sửa nhanh, không ảnh hưởng tới chỗ khác | Ghi lại, không tính vào tỉ lệ | Thiếu tag timeofday / weather / source; ảnh trùng trong file; thuộc tính thiếu giá trị |

Khi phân vân giữa hai mức, chọn mức cao hơn và ghi vào mục "Ca mơ hồ" của phiếu để lead quyết định.

## 2. Mức theo mã

| Mã | Mức | Khi nào nặng hơn hoặc nhẹ hơn |
| --- | --- | --- |
| QC1-01 tag camera | nặng | Tag camera thiếu hoặc sai là nặng; thiếu tag khác là nhẹ |
| QC1-02 đủ L1, R1 | nặng | |
| QC1-03 position | nặng | Gồm cả vạch không có trong GT (vẽ nhầm vật khác thành vạch) |
| QC1-04 tâm vạch, chiều, điểm dừng | chính | |
| QC1-05 vạch đứt, che | chính | |
| QC1-06 style, color, kind | chính | |
| QC1-07 vùng lái | chính | |
| QC1-08 đèn, màu | nặng / chính | Sai màu trên đèn hướng về xe (facing front) là nặng; các trường hợp khác là chính |
| QC1-09 facing, type, group, biển phụ | chính | |
| QC1-10 hình in, đủ biển | chính | |
| QC1-11 fisheye | chính | |
| QC1-12 file | nhẹ / nặng | File không mở được hoặc thiếu một trong hai file là nặng; label lạ, thuộc tính thiếu hoặc sai giá trị, ảnh trùng, ảnh ngoài lô là nhẹ (lỗi kéo theo được tính ở mã khác) |

Ngoài bảng trên, `road_check lint` còn in một cảnh báo **nhẹ** dưới mã QC1-08 / QC1-10 khi box thấp hơn 8 px. Đó là gợi ý tự kiểm (box nhỏ như vậy không bắt buộc), không phải lỗi chấm; `road_check check` không tính nó.

Bảng này khớp với `CODE_LEVEL` và cách `road_check check` gán mức. Nếu hai chỗ khác nhau thì code được coi là lỗi cần sửa, không phải thang mới.

## 3. Luật quyết định (giữ nguyên theo bài)

- Có ít nhất một lỗi nặng → **Rework**.
- Không có lỗi nặng, lỗi chính trên 5 % số nhãn đã kiểm → **Rework**.
- Còn câu hỏi chưa có lời đáp ảnh hưởng tới kết luận → **Hold** (chỉ người kiểm quyết định; `road_check` không bao giờ ra Hold).
- Còn lại → **Release**.

Mẫu số là số nhãn đã kiểm (shape cộng tag), không phải số ảnh.

## 4. Thang này dựa vào đâu

| Nguồn | Lấy gì | Không lấy gì |
| --- | --- | --- |
| ISO 2859-1 (lấy mẫu kiểm theo lô) | Ý tưởng chia lỗi thành các lớp theo mức nghiêm trọng: lớp A nghiêm trọng nhất, lớp B thấp hơn; mỗi lớp có ngưỡng chấp nhận (AQL) riêng, lớp nặng có ngưỡng nhỏ nhất | Bảng cỡ mẫu và AQL cụ thể. Chuẩn để người dùng tự chọn số lớp, lỗi thuộc lớp nào và AQL cho từng lớp |
| Thực hành kiểm hàng phổ biến (ANSI/ASQ Z1.4, tài liệu mua sắm) | Cách gọi critical / major / minor và quy ước lỗi critical không được chấp nhận (AQL 0) | Con số AQL của ngành sản xuất (ví dụ 2,5 % hay 4,0 %): đó là quy ước của từng hợp đồng |
| ISO/IEC 5259-4 mục 8.4.2 | Ba loại lỗi gán nhãn: bỏ sót, thừa, sai phạm vi (cột "Loại lỗi" trên phiếu) | Không có ngưỡng lỗi trong chuẩn |
| ISO/IEC 5259-4 mục 8.4.8 | Kiểm theo mẫu; với việc nội bộ rủi ro thấp lấy mẫu 5–10 % | Con số 5–10 % là tỉ lệ lấy mẫu, không phải ngưỡng đạt |
| ISO/IEC 5259-2 Điều 7 | Người dùng tự chọn phép đo và tự đặt tiêu chí chấp nhận | Chuẩn không cho ngưỡng |

Tóm lại: chuẩn cho **cấu trúc** (chia lớp lỗi, lớp nặng chặt nhất, kiểm theo mẫu); khóa học tự đặt **nội dung** (mã nào thuộc mức nào, ngưỡng 5 %). Ở dự án thật, chủ dữ liệu sẽ đặt hai thứ này theo rủi ro của sản phẩm.

## 5. Liên hệ với cách kiểm theo mẫu

Trong lab, người kiểm xem 6 ảnh của bạn mình, tức kiểm theo mẫu, không xem hết. Ở dự án thật:

- Lô càng rủi ro thì lấy mẫu càng nhiều; lô rủi ro thấp nội bộ có thể lấy 5–10 % (ISO/IEC 5259-4, 8.4.8).
- Mỗi lớp lỗi có ngưỡng riêng: lớp nặng thường không cho phép lỗi nào trong mẫu, lớp nhẹ cho phép nhiều hơn.
- Lô bị trả về được sửa rồi kiểm lại; bản gốc và bản sửa đều được giữ (8.4.9). Trong lab, việc này ghi bằng số lần nộp trong manifest bàn giao, xem [đặc tả bàn giao](delivery_road_v1.0.md).

---
AI20K · AI in Action · VinUni. Không đưa bản PDF của ISO cho học viên; tài liệu này chỉ trích ý.
