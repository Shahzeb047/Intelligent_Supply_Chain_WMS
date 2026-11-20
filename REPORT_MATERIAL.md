# OEL Report Material - SW 212 Data Structures & Algorithms
Project: **Intelligent Supply Chain & Warehouse Management System** · Group C - **Queue**

Copy these sections into your report (Word) and replace the bracketed items.

---

## 1. Chosen inventory system
Intelligent Supply Chain & Warehouse Management System - a multi-warehouse inventory platform for a distribution company with five warehouses, suppliers, purchase orders, customer orders, shipments and returns. The assigned data structure is a **Queue** (Group C).

## 2. Background and objectives
**Background.** A queue is a linear data structure that follows FIFO (First-In, First-Out): elements are inserted at the REAR and removed from the FRONT. Warehouses naturally work this way - customer orders, packed consignments and supplier trucks should be handled in the order they arrive.

**Objectives**
1. Implement the Queue from scratch (linked nodes, FRONT and REAR pointers) without using Python lists/deque for storage.
2. Perform CRUD on the inventory using the Queue (Enqueue / Dequeue).
3. Demonstrate FIFO with customer orders and warehouse dispatch.
4. Implement searching and sorting algorithms and compare their complexity.
5. Provide a professional interface with analytics, so the data structure is shown in a real application.

## 3. Tools and technologies
Python 3 + Flask (REST API), SQLite (persistent storage), JavaScript + Chart.js (interface and charts), VS Code, Git/GitHub. Justification: all tools are free, run locally and need no external services.

## 4. Implemented data structure (code to paste)
* `ds/queue.py` - classes `Node` and `Queue` (attributes `front`, `rear`; methods `enqueue`, `dequeue`, `peek`, `is_empty`, `size`, `display`, `find`, `update`, `remove`).
* `ds/algorithms.py` - `linear_search`, `binary_search`, `bubble_sort`, `selection_sort`, `insertion_sort`, `merge_sort`.
* Usage in the system: `backend/services.py` (order pipeline) and `backend/routes_inventory.py` (product CRUD).

Key idea to explain: `enqueue` creates a node, links it after `rear` and moves `rear`; `dequeue` returns `front`, moves `front` to `front.next` and sets `rear = None` when the queue becomes empty (underflow raises an error).

## 5. CRUD operations (with screenshots)
| Operation | Queue logic | Screenshot to attach |
|---|---|---|
| **Create** | `enqueue(product)` adds the product at the REAR of the Inventory Queue | Add Product form + product in table |
| **Read** | `find(pred)` rotates the queue once; listing traverses FRONT→REAR | product details, search results |
| **Update** | `update(pred, fn)` rotates the queue and edits the matching node | edit form + updated row |
| **Delete** | `remove(pred)` rotates and does not re-enqueue the match | confirmation + table afterwards |
| **Enqueue (orders)** | new order joins the REAR of the Order Queue | New Order form + queue strip |
| **Dequeue (orders)** | *Process Next* removes the FRONT order, confirms it | queue strip before/after |
| **Dispatch** | packed order enters the Dispatch Queue, *Dispatch Next* dequeues it and creates a shipment | shipments page |

Explain each operation in 3-4 lines (what happens to FRONT, REAR and `size`). The **DSA Visualization → Queue visualizer** shows these pointer changes step by step - capture its steps.

## 6. Algorithm analysis
* Queue: enqueue, dequeue, peek, is_empty - **O(1)**. Read/update/delete by key need rotation - **O(n)** (a queue is not meant for random access).
* Searching: linear **O(n)**, binary **O(log n)** (needs sorted data - the system sorts first with merge sort and refuses unsorted data).
* Sorting: bubble, selection, insertion **O(n²)**; merge sort **O(n log n)**.
* Use the **Algorithms lab → Performance benchmark** (n = 300 or 1000) and paste the table/chart: it shows real comparison counts (e.g. bubble ≈ 44,800 vs merge ≈ 2,100 comparisons for n = 300).

## 7. Results
* All CRUD operations work and persist in SQLite; stock levels update automatically after valid movements.
* FIFO is enforced: only the order at the FRONT of the Order Queue can be processed; cancelling an order removes it from the middle by rotation.
* Invalid operations are blocked (dispatching more than available stock, exceeding warehouse capacity, duplicate SKU, binary search on unsorted data).
* Role-based access (administrator, manager, employee) restricts pages and data per warehouse.
* The dashboard and analytics display real calculated data with date-range filters; reports export to PDF, Excel and CSV.

## 8. Conclusion
The Queue is a natural fit for order processing and dispatch where fairness (oldest first) matters. Constant-time enqueue/dequeue makes the pipeline efficient, while the O(n) cost of reading or deleting from the middle shows the trade-off of the structure. Implementing the structure from scratch and animating it made its unique characteristics - FRONT/REAR pointers, FIFO order, underflow - clear.

## 9. Recommendations for future improvement
1. Add a **priority queue** (express orders) and a **circular queue** for fixed-size dock slots.
2. Replace rotation-based search with an index (hash map) alongside the queue for O(1) lookups.
3. Real barcode scanner and mobile app for warehouse staff.
4. Demand forecasting from the movement history; automatic purchase order suggestions.
5. Move from SQLite to PostgreSQL and add audit-grade logging for multi-site deployment.

## 10. Links
* GitHub repository: **[paste your link]**
* Demo video (Google Drive): **[paste your link]**

### Suggested video flow (5-7 minutes)
Login → Dashboard (KPIs, charts, filters) → Add/Edit/Delete product → search & sort with algorithms → New order → Process Next → Mark packed → Dispatch Next → Shipment timeline → DSA Visualization (enqueue, dequeue, search, delete step-by-step) → Algorithms lab + benchmark → Reports export → dark mode / roles.
