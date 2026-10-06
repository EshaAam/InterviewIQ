---
title: Data structures and algorithms
topic: dsa
license: hand-written for InterviewIQ
url:
---

# Data structures and algorithms

## What does Big-O notation describe, and what does it hide?

Big-O describes how the running time or memory of an algorithm grows as the
input grows, ignoring constant factors. O(n) grows linearly, O(n log n) is
typical of good sorting, O(n²) appears with nested loops over the same data.

It hides constants and real hardware effects. An O(n) algorithm with a large
constant can be slower than an O(n log n) one for realistic sizes, and an array
scan that is friendly to the CPU cache can beat a theoretically better linked
structure. It also matters which case is described — worst, average or best —
and whether the input size is actually large enough for growth to dominate.

## When is a hash map the right tool?

A hash map gives average O(1) insert and lookup by key, so it turns "have I seen
this before?" and "how many times does this appear?" from nested loops into a
single pass. Two Sum, counting frequencies, grouping anagrams and caching results
all use it.

The trade-offs: no ordering (use a sorted map or tree when order matters),
extra memory, and a worst case of O(n) when many keys collide. Keys must be
hashable and must not change after insertion.

## When would you use an array versus a linked list?

Arrays store elements next to each other, giving O(1) access by index and good
cache performance, but inserting or deleting in the middle shifts elements, O(n).
Linked lists insert and delete in O(1) once you hold the node, but finding a
position takes O(n) and each node costs extra memory for pointers.

In practice dynamic arrays win most of the time because of cache behaviour.
Linked lists are still useful when you hold references to nodes and need
constant-time removal, as in an LRU cache built from a hash map plus a doubly
linked list.

## What are the two-pointer and sliding-window techniques?

Two pointers move through a sequence from both ends or at different speeds,
replacing a nested loop with a single pass: finding a pair that sums to a target
in a sorted array, removing duplicates in place, or detecting a cycle with a fast
and a slow pointer.

A sliding window keeps a range `[left, right]` and moves its edges to maintain a
condition, which solves "longest substring without repeating characters" or
"smallest subarray with sum at least k" in O(n). The window grows on the right
and shrinks on the left whenever the condition breaks, usually with a hash map
tracking what is inside.

## How can binary search be used beyond searching a sorted array?

Binary search halves the search space each step, giving O(log n). It applies
whenever a condition is false up to some point and true after it, not only to
finding a value in a sorted array.

That makes it useful for "binary search on the answer": the minimum ship
capacity to deliver packages within D days, or the smallest maximum page load
when splitting books. You test whether a candidate answer is feasible and halve
the range. The common bugs are off-by-one errors and infinite loops, avoided by
being precise about whether the bounds are inclusive.

## When do you use BFS and when DFS?

Breadth-first search explores level by level with a queue, so in an unweighted
graph it finds the shortest path in number of steps — the minimum moves in a
grid, the fewest connections between two people.

Depth-first search goes as deep as possible first, with recursion or a stack. It
suits exploring everything reachable, counting connected components, detecting
cycles and topological sorting. Both run in O(V + E) and must mark visited nodes
to avoid infinite loops on cycles. For weighted shortest paths, use Dijkstra's
algorithm instead.

## How do you recognise a dynamic programming problem?

Two signs: the problem can be broken into smaller versions of itself, and those
smaller problems repeat. Asking for a count of ways, a minimum or maximum cost,
or whether something is possible often points to dynamic programming —
climbing stairs, coin change, longest common subsequence, knapsack.

Define the state precisely (what does `dp[i]` mean?), write the transition from
smaller states, set the base cases, and choose the order. Start with recursion
plus memoisation if that is easier to think about, then convert to a bottom-up
table, and reduce memory when each state only depends on the previous row.

## When is a stack or a queue the right structure?

A stack (last in, first out) fits anything that needs to return to the most
recent unfinished item: matching brackets, undo, evaluating expressions, and
replacing recursion. A monotonic stack, which keeps elements in sorted order,
solves "next greater element" and "largest rectangle in a histogram" in O(n).

A queue (first in, first out) fits processing in arrival order — BFS, task
scheduling, buffering. A priority queue, usually a heap, always returns the
smallest or largest item in O(log n), which is what Dijkstra's algorithm and
"top k" problems need.

## Which sorting algorithms should you know, and what is stability?

Merge sort is O(n log n) in every case and stable, but needs extra memory. Quick
sort is O(n log n) on average and fast in practice, but O(n²) in the worst case
with bad pivots. Heap sort is O(n log n) with constant extra memory but is not
stable. Counting and radix sort can be linear when keys are small integers.

A sort is stable if equal elements keep their original order, which matters when
sorting by one field after another — sort by date, then stably by name. Most
language built-ins use a hybrid such as Timsort or introsort, so in practice you
call the library and choose the right comparator.
