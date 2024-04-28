# memory_pool.pyx
from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize
from threading import Lock
from orso.tools import random_int
from libcpp.vector cimport vector

cdef struct MemorySegment:
    int start
    int length

cdef class MemoryPool:
    cdef:
        unsigned char* pool
        public int size
        public vector[MemorySegment] free_segments
        public dict used_segments
        public str name
        public int commits, failed_commits, reads, read_locks, l1_compaction, l2_compaction, releases
        object lock

    def __cinit__(self, int size, str name="Memory Pool"):
        if size <= 0:
            raise ValueError("MemoryPool size must be a positive integer")
        self.size = size
        self.pool = <unsigned char*>malloc(size * sizeof(unsigned char))
        if not self.pool:
            raise MemoryError("Failed to allocate memory pool")
        self.name = name
        self.free_segments = [MemorySegment(0, size)]
        self.used_segments = {}
        self.lock = Lock()
        # Initialize statistics
        self.commits = 0
        self.failed_commits = 0
        self.reads = 0
        self.read_locks = 0
        self.l1_compaction = 0
        self.l2_compaction = 0
        self.releases = 0

    def __dealloc__(self):
        if self.pool is not NULL:
            free(self.pool)

    def _find_free_segment(self, int size) -> int:
        cdef int i
        cdef MemorySegment segment
        for i in range(len(self.free_segments)):
            segment = self.free_segments[i]
            if segment.length >= size:
                return i
        return -1

    def _level1_compaction(self):
        cdef int i, n
        cdef MemorySegment last_segment, current_segment, segment
        cdef vector[MemorySegment] sorted_segments

        self.l1_compaction += 1
        i = 1
        n = len(self.free_segments)

        sorted_segments = sorted(self.free_segments, key=lambda x: x["start"])
        new_free_segments = [sorted_segments[0]]

        for segment in self.free_segments[1:]:
            last_segment = new_free_segments[-1]
            if last_segment.start + last_segment.length == segment.start:
                # If adjacent, merge by extending the last segment
                last_segment.length += segment.length
            else:
                # If not adjacent, just add the segment to the new list
                new_free_segments.append(segment)

        self.free_segments = new_free_segments

    def _level2_compaction(self):
        """
        Aggressively compacts by pushing all free memory to the end (Level 2 compaction).

        This is slower, but ensures we get the maximum free space.
        """
        cdef MemorySegment segment
        cdef long segment_id
        cdef int offset = 0

        self.l2_compaction += 1

        total_free_space = sum(segment.length for segment in self.free_segments)
        compacted_start = self.size - total_free_space
        self.free_segments = [MemorySegment(compacted_start, total_free_space)]

        for segment_id, segment in sorted(self.used_segments.items(), key=lambda x: x[1]["start"]):
            memcpy(self.pool + offset, self.pool + segment.start, segment.length)
            segment.start = offset
            self.used_segments[segment_id] = segment
            offset += segment.length

    def commit(self, bytes data) -> long:
        cdef int len_data = len(data)
        cdef int segment_index
        cdef MemorySegment segment
        cdef long ref_id = random_int() 

        # special case for 0 byte segments
        if len_data == 0:
            new_segment = MemorySegment(0, 0)
            ref_id = random_int()
            self.used_segments[ref_id] = new_segment
            self.commits += 1
            return ref_id

        total_free_space = sum(segment.length for segment in self.free_segments)
        if total_free_space < len_data:
            self.failed_commits += 1
            return None

        with self.lock:
            segment_index = self._find_free_segment(len_data)
            if segment_index == -1:
                self._level1_compaction()
                segment_index = self._find_free_segment(len_data)
                if segment_index == -1:
                    self._level2_compaction()
                    segment_index = self._find_free_segment(len_data)
                    if segment_index == -1:
                        return None  # No space available

            segment = self.free_segments[segment_index]
            self.free_segments.erase(self.free_segments.begin() + segment_index)
            if segment.length > len_data:
                self.free_segments.push_back(MemorySegment(segment.start + len_data, segment.length - len_data))

            memcpy(self.pool + segment.start, PyBytes_AsString(data), len_data)
            self.used_segments[ref_id] = MemorySegment(segment.start, len_data)
            return ref_id

    def read(self, long ref_id) -> bytes:
        cdef MemorySegment segment
        cdef char* char_ptr = <char*> self.pool
        with self.lock:
            if ref_id not in self.used_segments:
                raise ValueError("Invalid reference ID.")
            segment = self.used_segments[ref_id]
            
            data = PyBytes_FromStringAndSize(char_ptr + segment.start, segment.length)
            return data

    def release(self, long ref_id):
        with self.lock:
            if ref_id not in self.used_segments:
                raise ValueError(f"Invalid reference ID - {ref_id}.")
            segment = self.used_segments.pop(ref_id)
            self.free_segments.push_back(segment)

    def available_space(self) -> int:
        return sum(segment.length for segment in self.free_segments)