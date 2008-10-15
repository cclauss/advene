"""
I define the class of relations.
"""

from weakref import ref

from advene import _RAISE
from advene.model.core.element \
  import PackageElement, ANNOTATION, RELATION
from advene.model.core.content import WithContentMixin

class Relation(PackageElement, WithContentMixin):
    """
    I expose the protocol of a basic collection, to give access to the members
    of a relation. I also try to efficiently cache the results I know.
    """

    ADVENE_TYPE = RELATION

    def __init__(self, owner, id):
        PackageElement.__init__(self, owner, id)
        self._cache = None

    def __len__(self):
        L = self._cache
        if L is None:
            o = self._owner
            c = o._backend.count_members(o._id, self._id)
            self._cache = [None,] * c
        else:
            c = len(L)
        return c

    def __iter__(self):
        o = self._owner
        it = o._backend.iter_members(o._id, self._id)
        L = self._cache
        if L is None:
            it = list(it)
            L = self._cache = [None,] * len(it)

        for i,id in enumerate(it):
            e = L[i]
            if e is None:
                e = L[i] = self._owner.get_element(id)
            yield e

    def __getitem__(self, i):
        if isinstance(i, slice): return self._get_slice(i)
        return self.get_member(i, _RAISE)

    def __setitem__(self, i, a):
        if isinstance(i, slice): return self._set_slice(i, a)
        assert a.ADVENE_TYPE == ANNOTATION
        o = self._owner
        assert o._can_reference(a)
        L = self._cache
        if L is not None:
            c = len(L)
        else:
            c = self.__len__() # also prepares cache
            L = self._cache
        assert -c <= i < c
        idref = a.make_idref_for(o)
        o._backend.update_member(o._id, self._id, idref, i)
        L[i] = a

    def __delitem__(self, i):
        if isinstance(i, slice): return self._del_slice(i)
        L = self._cache
        if L is not None:
            c = len(L)
        else:
            c = self.__len__() # also prepares cache
            L = self._cache
        assert -c <= i < c
        o = self._owner
        o._backend.remove_member(o._id, self._id, i)
        del L[i]

    def _get_slice(self, s):
        c = self.__len__() # also prepares cache
        for i in range(c)[s]:
            self[i] # retrieve ith element
        return self._cache[s]

    def _set_slice(self, s, annotations):
        c = self.__len__() # also prepares cache
        indices = range(c)[s]
        same_length = (len(annotations) == len(indices))
        if s.step is None and not same_length:
            self._del_slice(s)
            insertpoint = s.start or 0
            for a in annotations:
                self.insert(insertpoint, a)
                insertpoint += 1
        else:
            if not same_length:
                raise ValueError("attempt to assign sequence of size %s to "
                                 "extended slice of size %s"
                                 % (len(annotations), len(indices)))
            for i,j in enumerate(indices):
                self.__setitem__(j, annotations[i])
        
    def _del_slice(self,s):
        c = self.__len__() # also prepares cache
        indices = range(c)[s]
        indices.sort()
        offset = 0
        for offset, i in enumerate(indices):
            del self[i-offset]

    def insert(self, i, a):
        o = self._owner
        c = self.__len__() # also prepares cache
        assert a.ADVENE_TYPE == ANNOTATION
        assert o._can_reference(a)
        idref = a.make_idref_for(o)
        if i > c : i = c
        if i < -c: i = 0
        if i < 0 : i += c 
        o._backend.insert_member(o._id, self._id, idref, i)
        self._cache.insert(i,a)
        
    def append(self, a):
        o = self._owner
        c = self.__len__() # also prepares cache
        assert a.ADVENE_TYPE == ANNOTATION
        assert o._can_reference(a)
        idref = a.make_idref_for(o)
        o._backend.insert_member(o._id, self._id, idref, -1)
        self._cache.append(a)

    def extend(self, annotations):
        for a in annotations:
            self.append(a)

    def get_member(self, i, default=None):
        """Return element with index i, or default if it can not be retrieved.

        Use self[i] instead, unless you want to avoid exceptions on retrieval
        errors. Note also that IndexErrors are not avoided by this method.
        """
        L = self._cache
        if L is None:
            self.__len__() # prepare cache
            L = self._cache
        r = L[i] # also ensures that i is a valid index
        if r is None:
            o = self._owner
            id = o._backend.get_member(o._id, self._id, i)
            r = o.get_element(id, default)
            if r is not default: L[i] = r
        return r

