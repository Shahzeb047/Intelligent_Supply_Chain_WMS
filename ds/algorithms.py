"""
ds/algorithms.py  -  Searching & sorting written from scratch
=============================================================
No built-in sorted()/list.sort()/bisect is used for the algorithms below.

Searching : linear_search (O(n)), binary_search (O(log n), needs SORTED data)
Sorting   : bubble (O(n^2)), selection (O(n^2)), insertion (O(n^2)),
            merge (O(n log n))

Every function works on a list of records (dicts or numbers) plus a `key`
function, counts comparisons / swaps, and can optionally record "frames"
(a snapshot of the array + highlighted indexes) through `rec` so the web UI
can replay the real execution step by step.
"""
import time


class Stats:
    def __init__(self):
        self.comparisons = 0
        self.swaps = 0      # swaps (bubble/selection) or moves/writes (insertion/merge)


def _norm(v):
    return v.lower() if isinstance(v, str) else v


def _less(a, b, st):
    st.comparisons += 1
    return _norm(a) < _norm(b)


def _greater(a, b, st):
    st.comparisons += 1
    return _norm(a) > _norm(b)


def _frame(rec, arr, key, msg, hl=(), kind="compare", extra=None):
    if rec is None:
        return
    f = {"arr": [key(x) for x in arr], "hl": list(hl), "msg": msg, "kind": kind}
    if extra:
        f.update(extra)
    rec.append(f)


# ---------------------------------------------------------------- sorting
def bubble_sort(items, key=lambda x: x, desc=False, rec=None):
    a, st = list(items), Stats()
    n = len(a)
    _frame(rec, a, key, "Start bubble sort: compare neighbours and swap if out of order", kind="start")
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            out = _less(key(a[j]), key(a[j + 1]), st) if desc else _greater(key(a[j]), key(a[j + 1]), st)
            _frame(rec, a, key, f"Compare positions {j} and {j + 1}: {key(a[j])} vs {key(a[j + 1])}", (j, j + 1))
            if out:
                a[j], a[j + 1] = a[j + 1], a[j]
                st.swaps += 1
                swapped = True
                _frame(rec, a, key, f"Swap -> {key(a[j])} and {key(a[j + 1])} exchanged", (j, j + 1), "swap")
        if not swapped:
            break
    _frame(rec, a, key, "Sorted!", kind="done")
    return a, st


def selection_sort(items, key=lambda x: x, desc=False, rec=None):
    a, st = list(items), Stats()
    n = len(a)
    _frame(rec, a, key, "Start selection sort: pick the smallest remaining item each pass", kind="start")
    for i in range(n - 1):
        m = i
        for j in range(i + 1, n):
            better = _greater(key(a[j]), key(a[m]), st) if desc else _less(key(a[j]), key(a[m]), st)
            _frame(rec, a, key, f"Pass {i + 1}: compare {key(a[j])} with current best {key(a[m])}", (m, j))
            if better:
                m = j
        if m != i:
            a[i], a[m] = a[m], a[i]
            st.swaps += 1
            _frame(rec, a, key, f"Place {key(a[i])} at position {i}", (i, m), "swap")
    _frame(rec, a, key, "Sorted!", kind="done")
    return a, st


def insertion_sort(items, key=lambda x: x, desc=False, rec=None):
    a, st = list(items), Stats()
    _frame(rec, a, key, "Start insertion sort: insert each item into the sorted left part", kind="start")
    for i in range(1, len(a)):
        cur, j = a[i], i - 1
        _frame(rec, a, key, f"Take {key(cur)} and find its place in the sorted part", (i,))
        while j >= 0:
            move = _less(key(a[j]), key(cur), st) if desc else _greater(key(a[j]), key(cur), st)
            if not move:
                break
            a[j + 1] = a[j]
            st.swaps += 1
            _frame(rec, a, key, f"Shift {key(a[j + 1])} one step right", (j, j + 1), "swap")
            j -= 1
        a[j + 1] = cur
        _frame(rec, a, key, f"Insert {key(cur)} at position {j + 1}", (j + 1,), "swap")
    _frame(rec, a, key, "Sorted!", kind="done")
    return a, st


def merge_sort(items, key=lambda x: x, desc=False, rec=None):
    a, st = list(items), Stats()
    _frame(rec, a, key, "Start merge sort: split in halves, sort each, merge them", kind="start")

    def msort(lo, hi):                       # sorts a[lo:hi]
        if hi - lo < 2:
            return
        mid = (lo + hi) // 2
        msort(lo, mid)
        msort(mid, hi)
        left, right = a[lo:mid], a[mid:hi]   # temporary halves
        i = j = 0
        k = lo
        while i < len(left) and j < len(right):
            take_left = (not _less(key(left[i]), key(right[j]), st)) if desc else (not _less(key(right[j]), key(left[i]), st))
            if take_left:
                a[k] = left[i]; i += 1
            else:
                a[k] = right[j]; j += 1
            st.swaps += 1
            _frame(rec, a, key, f"Merging [{lo}..{hi - 1}]: write {key(a[k])} at position {k}", (k,), "swap")
            k += 1
        while i < len(left):
            a[k] = left[i]; i += 1; k += 1; st.swaps += 1
            _frame(rec, a, key, f"Copy remaining left item {key(a[k - 1])}", (k - 1,), "swap")
        while j < len(right):
            a[k] = right[j]; j += 1; k += 1; st.swaps += 1
            _frame(rec, a, key, f"Copy remaining right item {key(a[k - 1])}", (k - 1,), "swap")

    msort(0, len(a))
    _frame(rec, a, key, "Sorted!", kind="done")
    return a, st


SORTERS = {"bubble": bubble_sort, "selection": selection_sort,
           "insertion": insertion_sort, "merge": merge_sort}


def sort_records(items, key, algo="merge", desc=False):
    """Sort with the chosen algorithm; returns (sorted_list, info dict)."""
    fn = SORTERS.get(algo, merge_sort)
    t0 = time.perf_counter()
    out, st = fn(items, key, desc)
    ms = (time.perf_counter() - t0) * 1000
    return out, {"algorithm": algo, "comparisons": st.comparisons, "moves": st.swaps,
                 "ms": round(ms, 3), "n": len(out)}


def is_sorted(items, key, desc=False):
    for i in range(len(items) - 1):
        a, b = _norm(key(items[i])), _norm(key(items[i + 1]))
        if (a < b) if desc else (a > b):
            return False
    return True


# -------------------------------------------------------------- searching
def linear_search(items, target, key=lambda x: x, rec=None, contains=False):
    """Check every element one by one.  O(n)"""
    st = Stats()
    t = _norm(target)
    hits = []
    for i, it in enumerate(items):
        v = _norm(key(it))
        st.comparisons += 1
        ok = (t in v) if (contains and isinstance(v, str)) else (v == t)
        if rec is not None:
            _frame(rec, items, key, f"Check index {i}: {key(it)} {'==' if ok else '!='} {target}", (i,),
                   "found" if ok else "compare")
        if ok:
            hits.append(i)
            if not contains:
                break
    return hits, st


def binary_search(items, target, key=lambda x: x, rec=None):
    """
    Halve the search range each step.  O(log n)
    PRECONDITION: `items` must be sorted ascending by `key` (checked).
    """
    if not is_sorted(items, key):
        raise ValueError("Binary search needs data sorted in ascending order. Sort it first.")
    st = Stats()
    t = _norm(target)
    lo, hi = 0, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        v = _norm(key(items[mid]))
        st.comparisons += 1
        if rec is not None:
            _frame(rec, items, key, f"lo={lo}, hi={hi}, mid={mid}: look at {key(items[mid])}", (mid,), "compare",
                   {"lo": lo, "hi": hi, "mid": mid})
        if v == t:
            if rec is not None:
                _frame(rec, items, key, f"Found {target} at index {mid}", (mid,), "found", {"lo": lo, "hi": hi, "mid": mid})
            return [mid], st
        if v < t:
            lo = mid + 1
        else:
            hi = mid - 1
    if rec is not None:
        _frame(rec, items, key, f"{target} is not in the list", (), "done")
    return [], st


ALGO_INFO = [
    {"id": "linear", "name": "Linear Search", "type": "search", "best": "O(1)", "avg": "O(n)", "worst": "O(n)", "space": "O(1)",
     "purpose": "Find an item by checking every element one after another. Works on unsorted data.",
     "steps": ["Start at index 0", "Compare the element with the target", "If equal -> found, stop", "Otherwise move to the next index", "If the end is reached -> not found"]},
    {"id": "binary", "name": "Binary Search", "type": "search", "best": "O(1)", "avg": "O(log n)", "worst": "O(log n)", "space": "O(1)",
     "purpose": "Find an item in SORTED data by repeatedly halving the search range.",
     "steps": ["Set lo = 0 and hi = n-1", "mid = (lo + hi) / 2", "If a[mid] == target -> found", "If a[mid] < target -> lo = mid + 1, else hi = mid - 1", "Repeat while lo <= hi"]},
    {"id": "bubble", "name": "Bubble Sort", "type": "sort", "best": "O(n)", "avg": "O(n^2)", "worst": "O(n^2)", "space": "O(1)",
     "purpose": "Repeatedly compare neighbouring items and swap them when they are in the wrong order.",
     "steps": ["Compare a[j] and a[j+1]", "Swap if a[j] > a[j+1]", "After each pass the largest item bubbles to the end", "Stop when a full pass makes no swap"]},
    {"id": "selection", "name": "Selection Sort", "type": "sort", "best": "O(n^2)", "avg": "O(n^2)", "worst": "O(n^2)", "space": "O(1)",
     "purpose": "Select the smallest remaining item and place it at the next position of the sorted part.",
     "steps": ["For position i find the minimum in a[i..n-1]", "Swap it with a[i]", "Move i one step right", "Repeat until i reaches n-1"]},
    {"id": "insertion", "name": "Insertion Sort", "type": "sort", "best": "O(n)", "avg": "O(n^2)", "worst": "O(n^2)", "space": "O(1)",
     "purpose": "Build the sorted array one item at a time by inserting each item into its correct place.",
     "steps": ["Take a[i] as the current item", "Shift larger items of the sorted part one step right", "Insert the current item in the gap", "Repeat for every i"]},
    {"id": "merge", "name": "Merge Sort", "type": "sort", "best": "O(n log n)", "avg": "O(n log n)", "worst": "O(n log n)", "space": "O(n)",
     "purpose": "Divide and conquer: split the array, sort both halves recursively, then merge them.",
     "steps": ["Split the array into two halves", "Recursively sort each half", "Merge: repeatedly take the smaller front item of the halves", "Copy any remaining items"]},
]
