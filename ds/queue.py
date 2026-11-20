"""
ds/queue.py  -  CUSTOM QUEUE (FIFO)  -  OEL Group C
====================================================
A genuine queue built from linked nodes with FRONT and REAR pointers.
No Python list / deque / queue module is used to store the data.

    FRONT -> [node] -> [node] -> [node] -> None
                                   ^
                                  REAR

Core operations (all O(1)):
    enqueue(x)   insert at REAR
    dequeue()    remove from FRONT (raises IndexError on underflow)
    peek()       read FRONT without removing
    is_empty()   size == 0
    display()    traverse FRONT -> REAR

CRUD helpers (O(n)).  A queue does NOT natively support access to the middle,
so Read / Update / Delete by key are done honestly by ROTATION:
    dequeue the front item, inspect it, enqueue it again at the rear -
    repeated `size` times.  FIFO order is preserved afterwards.
        find(pred)          READ
        update(pred, fn)    UPDATE
        remove(pred)        DELETE (the matching item is not re-enqueued)

Tracing:  set `queue.start_trace()` before an operation and read
`queue.stop_trace()` afterwards.  Every step records a snapshot of all nodes,
the FRONT/REAR pointers and a human readable message - this is what the
"DSA Visualization" page animates, so the animation is the real execution.
"""


class Node:
    """One link of the queue: data + pointer to the next node."""
    __slots__ = ("data", "next", "uid")

    def __init__(self, data, uid):
        self.data = data
        self.next = None
        self.uid = uid


class Queue:
    _uid_counter = 0

    def __init__(self, name="Queue", labeler=None):
        self.name = name
        self.front = None            # FRONT pointer (oldest element)
        self.rear = None             # REAR pointer  (newest element)
        self._size = 0
        self.enqueue_calls = 0
        self.dequeue_calls = 0
        self._labeler = labeler or (lambda d: str(d))
        self._trace = None

    # ------------------------------------------------------------ tracing
    def start_trace(self):
        self._trace = []

    def stop_trace(self):
        t, self._trace = self._trace or [], None
        return t

    def snapshot(self):
        """List of node descriptions FRONT -> REAR (used by the visualizer)."""
        out, cur = [], self.front
        while cur is not None:
            out.append({"uid": cur.uid, "label": self._labeler(cur.data),
                        "next": cur.next.uid if cur.next else None})
            cur = cur.next
        return out

    def _step(self, msg, hold=None, hl=None, kind="info"):
        if self._trace is None:
            return
        self._trace.append({
            "msg": msg, "kind": kind, "nodes": self.snapshot(),
            "front": self.front.uid if self.front else None,
            "rear": self.rear.uid if self.rear else None,
            "size": self._size, "hold": hold, "hl": hl,
        })

    # ------------------------------------------------------ core operations
    def enqueue(self, data):
        """Insert at REAR.  O(1)"""
        Queue._uid_counter += 1
        node = Node(data, Queue._uid_counter)
        label = self._labeler(data)
        self._step(f"Create a new node for '{label}' (next = None)", hold={"label": label}, kind="create")
        if self.rear is None:
            self.front = self.rear = node
            self._size += 1
            self._step("Queue was empty: FRONT = REAR = new node", hl=node.uid, kind="link")
        else:
            self.rear.next = node
            self._step(f"REAR.next now points to the new node", hl=node.uid, kind="link")
            self.rear = node
            self._size += 1
            self._step("Move the REAR pointer to the new node", hl=node.uid, kind="rear")
        self.enqueue_calls += 1
        return node

    def dequeue(self):
        """Remove and return the FRONT element.  O(1)"""
        if self.front is None:
            self._step("UNDERFLOW: queue is empty, nothing to dequeue", kind="error")
            raise IndexError(f"{self.name} is empty (underflow)")
        node = self.front
        label = self._labeler(node.data)
        self._step(f"FRONT points to '{label}' - this is the oldest item", hl=node.uid, kind="peek")
        self.front = node.next
        if self.front is None:
            self.rear = None
        self._size -= 1
        self.dequeue_calls += 1
        self._step(f"Move FRONT to the next node; '{label}' leaves the queue",
                   hold={"label": label}, kind="front")
        return node.data

    def peek(self):
        """Read the FRONT element without removing it.  O(1)"""
        if self.front is None:
            self._step("Queue is empty - peek returns None", kind="error")
            return None
        self._step(f"peek(): FRONT holds '{self._labeler(self.front.data)}'", hl=self.front.uid, kind="peek")
        return self.front.data

    def peek_rear(self):
        return None if self.rear is None else self.rear.data

    def is_empty(self):
        return self._size == 0

    def size(self):
        return self._size

    def __len__(self):
        return self._size

    def __iter__(self):
        """Read-only traversal FRONT -> REAR (display / reporting)."""
        cur = self.front
        while cur is not None:
            yield cur.data
            cur = cur.next

    def display(self):
        return " -> ".join(self._labeler(x) for x in self) + " -> None"

    def to_list(self):
        return list(self)

    def clear(self):
        while self._size:
            n = self.front
            self.front = n.next
            self._size -= 1
        self.rear = None
        self.enqueue_calls = 0
        self.dequeue_calls = 0

    # ------------------------------------------------------ CRUD by rotation
    def _rotate(self, predicate, on_match):
        """
        Rotate the queue once.  For each of the `size` items: dequeue it,
        test it, and (unless on_match says drop it) enqueue it again.
        Returns the first matching item or None.
        """
        found = None
        for _ in range(self._size):
            node = self.front
            self.front = node.next
            if self.front is None:
                self.rear = None
            self._size -= 1
            item = node.data
            label = self._labeler(item)
            self.dequeue_calls += 1
            if found is None and predicate(item):
                found = item
                keep = on_match(item)
                if keep:
                    self._relink(node)
                    self._step(f"Dequeue '{label}' -> MATCH -> enqueue it back at REAR", hl=node.uid, kind="match")
                else:
                    self._step(f"Dequeue '{label}' -> MATCH -> not re-enqueued (deleted)", hold={"label": label}, kind="delete")
            else:
                self._relink(node)
                self._step(f"Dequeue '{label}' -> no match -> enqueue it back at REAR", hl=node.uid, kind="rotate")
        return found

    def _relink(self, node):
        node.next = None
        if self.rear is None:
            self.front = self.rear = node
        else:
            self.rear.next = node
            self.rear = node
        self._size += 1
        self.enqueue_calls += 1

    def find(self, predicate):
        """READ: first element matching predicate (or None).  O(n)"""
        return self._rotate(predicate, lambda item: True)

    def update(self, predicate, updater):
        """UPDATE: apply updater(item) to the first match.  O(n)"""
        def apply(item):
            updater(item)
            return True
        return self._rotate(predicate, apply)

    def remove(self, predicate):
        """DELETE: remove the first match from the middle.  O(n)"""
        return self._rotate(predicate, lambda item: False)

    def __repr__(self):
        return f"{self.name}[{self.display()}]"
