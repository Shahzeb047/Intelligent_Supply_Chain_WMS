"""
demo_cli.py - console demo of the custom Queue (no web server, no database).
Run:  python demo_cli.py     -> use the output as screenshots for the report (CRUD proof).
"""
from ds.queue import Queue

q = Queue("Inventory Queue", labeler=lambda p: p["name"])

def show(title):
    print(f"\n--- {title} ---")
    print("   FRONT ->", q.display(), "<- REAR" if not q.is_empty() else "")
    print(f"   size={q.size()}  front={q.peek()['name'] if not q.is_empty() else None}  rear={q.peek_rear()['name'] if not q.is_empty() else None}")

print("=" * 64); print(" QUEUE CRUD DEMO - Intelligent Supply Chain & Warehouse System"); print("=" * 64)
print("\n[CREATE] enqueue() inserts at the REAR - O(1)")
for n, qty in [("Laptop", 20), ("Mouse", 150), ("Keyboard", 60), ("Monitor", 25)]:
    q.enqueue({"name": n, "qty": qty}); print("   enqueue ->", n)
show("After CREATE")
print("\n[READ] find() rotates the queue (dequeue -> check -> enqueue) - O(n)")
print("   found:", q.find(lambda p: p["name"] == "Keyboard")); show("FIFO order preserved after READ")
print("\n[UPDATE] update() rotates the queue and edits the match - O(n)")
q.update(lambda p: p["name"] == "Mouse", lambda p: p.update(qty=200)); print("   Mouse qty -> 200"); show("After UPDATE")
print("\n[DELETE] remove() rotates the queue and skips the match - O(n)")
print("   removed:", q.remove(lambda p: p["name"] == "Laptop")["name"]); show("After DELETE")
print("\n[DEQUEUE] dequeue() serves the OLDEST item (FIFO) - O(1)")
print("   served:", q.dequeue()["name"]); show("After DEQUEUE")
print("\n[UNDERFLOW] dequeue on an empty queue")
while not q.is_empty(): q.dequeue()
try: q.dequeue()
except IndexError as e: print("   caught ->", e)
print(f"\nTotal enqueue calls: {q.enqueue_calls} | dequeue calls: {q.dequeue_calls} (rotations included)")
