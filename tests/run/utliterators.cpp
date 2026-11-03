#include "tier0/utlvector.h"
#include "tier0/utlleanvector.h"
#include "tier0/utllinkedlist.h"
#include "tier0/utlrbtree.h"
#include "tier0/utlmap.h"
#include "tier0/utldict.h"
#include "tier0/utlhashmap.h"
#include "tier0/utlhashmaplarge.h"
#include "tier0/utlstring.h"
#include "tier0/utlblockvector.h"
#include "tier0/utlhashtable.h"
#include "tier0/utlstringmap.h"
#include "tier0/utltshash.h"
#include "tier0/utlqueue.h"
#include "tier0/utlvectorultraconservative.h"

#include <algorithm>
#include <iterator>
#include <numeric>
#include <stdio.h>
#include <string.h>

static int g_nFailures = 0;

#define CHECK( expr ) \
	do \
	{ \
		if ( !( expr ) ) \
		{ \
			printf( "%s:%d: CHECK( %s ) failed\n", __FILE__, __LINE__, #expr ); \
			++g_nFailures; \
		} \
	} while ( 0 )

static const int s_Values[] = { 5, 3, 9, 1, 7, 2, 8 };
static const int s_Sorted[] = { 1, 2, 3, 5, 7, 8, 9 };
static const int s_nValues = sizeof( s_Values ) / sizeof( s_Values[0] );

// Walks the container forwards, as const too, and checks it yields expected in order
template < typename Container >
static bool YieldsInOrder( Container &c, const int *expected, int count )
{
	int i = 0;
	for ( int &v : c )
	{
		if ( i >= count || v != expected[i] )
			return false;
		++i;
	}
	if ( i != count )
		return false;

	i = 0;
	const Container &cc = c;
	for ( const int &v : cc )
	{
		if ( i >= count || v != expected[i] )
			return false;
		++i;
	}
	return i == count && std::distance( c.begin(), c.end() ) == count;
}

// Walks a bidirectional container backwards from end()
template < typename Container >
static bool YieldsReversed( const Container &c, const int *expected, int count )
{
	int i = count;
	for ( auto it = c.end(); it != c.begin(); )
	{
		--it;
		if ( --i < 0 || *it != expected[i] )
			return false;
	}
	return i == 0;
}

// Doubles every element through the non-const iterator
template < typename Container >
static void DoubleAll( Container &c )
{
	for ( int &v : c )
		v *= 2;
}

template < typename Vector >
static void TestVector( Vector &vec, int count )
{
	CHECK( vec.begin() == vec.end() );

	int *expected = new int[count];
	for ( int i = 0; i < count; i++ )
	{
		expected[i] = i * 3 + 1;
		vec.AddToTail( expected[i] );
	}
	CHECK( YieldsInOrder( vec, expected, count ) );
	CHECK( YieldsReversed( vec, expected, count ) );
	CHECK( std::accumulate( vec.begin(), vec.end(), 0 ) == std::accumulate( expected, expected + count, 0 ) );
	CHECK( std::find( vec.begin(), vec.end(), expected[count / 2] ) - vec.begin() == count / 2 );

	DoubleAll( vec );
	for ( int i = 0; i < count; i++ )
		expected[i] *= 2;
	CHECK( YieldsInOrder( vec, expected, count ) );

	vec.RemoveAll();
	CHECK( vec.begin() == vec.end() );
	delete[] expected;
}

static void TestVectors()
{
	{
		CUtlVector<int> vec;
		TestVector( vec, 100 );
	}

	{
		// Grows past its inline storage
		CUtlVectorFixedGrowable<int, 4> vec;
		TestVector( vec, 100 );
	}

	{
		CUtlVectorFixed<int, 16> vec;
		TestVector( vec, 16 );
	}

	{
		CUtlVectorConservative<int> vec;
		TestVector( vec, 100 );
	}

	{
		CUtlVectorRawAllocator<int> vec;
		TestVector( vec, 100 );
	}

	{
		// Spans several blocks
		CUtlBlockVector<int> vec;
		TestVector( vec, 1000 );
	}

	{
		CUtlLeanVector<int> vec;
		TestVector( vec, 100 );
	}

	{
		CUtlVectorUltraConservative<int> vec;
		TestVector( vec, 100 );
	}

	{
		CUtlVector<int> vec;
		for ( int v : s_Values )
			vec.AddToTail( v );
		vec.Sort();
		CHECK( YieldsInOrder( vec, s_Sorted, s_nValues ) );
	}
}

template < typename List >
static void TestList( List &list )
{
	CHECK( list.begin() == list.end() );
	CHECK( list.Count() == 0 );

	// 2, 1, 3, 4 with a removed element in the middle
	list.AddToTail( 1 );
	auto removed = list.AddToTail( 100 );
	list.AddToTail( 3 );
	list.AddToHead( 2 );
	list.AddToTail( 4 );
	CHECK( list.Count() == 5 );
	list.Remove( removed );
	CHECK( list.Count() == 4 );
	CHECK( !list.IsValidIndex( removed ) );

	const int expected[] = { 2, 1, 3, 4 };
	CHECK( YieldsInOrder( list, expected, 4 ) );
	CHECK( YieldsReversed( list, expected, 4 ) );

	int nVisited = 0;
	FOR_EACH_LL( list, it )
	{
		CHECK( nVisited < 4 && list[it] == expected[nVisited] );
		++nVisited;
	}
	CHECK( nVisited == 4 );

	DoubleAll( list );
	const int doubled[] = { 4, 2, 6, 8 };
	CHECK( YieldsInOrder( list, doubled, 4 ) );

	CHECK( list.AddToTail( 5 ) == removed );
	CHECK( list.Count() == 5 );

	list.RemoveAll();
	CHECK( list.begin() == list.end() );
	CHECK( list.Count() == 0 );

	list.AddToTail( 1 );
	CHECK( list.Count() == 1 );
	list.Purge();
	CHECK( list.Count() == 0 );
}

static void TestLinkedLists()
{
	{
		CUtlLinkedList<int> list;
		TestList( list );
	}

	{
		CUtlLinkedList<int, unsigned short, true> list;
		TestList( list );
	}

	{
		CUtlLinkedList<int, unsigned int> list;
		TestList( list );
	}

	{
		CUtlFixedLinkedList<int> list;
		TestList( list );
	}

	{
		CUtlBlockLinkedList<int> list;
		TestList( list );
	}
}

static void TestRBTree()
{
	CUtlRBTree<int> tree;
	CHECK( tree.begin() == tree.end() );

	for ( int v : s_Values )
		tree.Insert( v );

	CHECK( YieldsInOrder( tree, s_Sorted, s_nValues ) );
	CHECK( YieldsReversed( tree, s_Sorted, s_nValues ) );

	tree.Remove( 5 );
	const int expected[] = { 1, 2, 3, 7, 8, 9 };
	CHECK( YieldsInOrder( tree, expected, 6 ) );
}

static void TestOrderedMap()
{
	CUtlOrderedMap<int, CUtlString> map;
	CHECK( map.begin() == map.end() );

	for ( int v : s_Values )
	{
		char buf[16];
		snprintf( buf, sizeof( buf ), "v%d", v );
		map.Insert( v, buf );
	}

	int i = 0;
	for ( auto &node : map )
	{
		char buf[16];
		snprintf( buf, sizeof( buf ), "v%d", s_Sorted[i] );
		CHECK( i < s_nValues && node.key == s_Sorted[i] && node.elem == buf );
		node.elem = "changed";
		++i;
	}
	CHECK( i == s_nValues );

	i = 0;
	const CUtlOrderedMap<int, CUtlString> &cmap = map;
	for ( const auto &node : cmap )
	{
		CHECK( node.key == s_Sorted[i] && node.elem == "changed" );
		++i;
	}
	CHECK( i == s_nValues );

	i = s_nValues;
	for ( auto it = map.end(); it != map.begin(); )
	{
		--it;
		CHECK( it->key == s_Sorted[--i] );
	}
	CHECK( i == 0 );
}

static void TestDict()
{
	CUtlDict<int> dict;
	CHECK( dict.begin() == dict.end() );

	dict.Insert( "charlie", 3 );
	dict.Insert( "alpha", 1 );
	dict.Insert( "delta", 4 );
	dict.Insert( "bravo", 2 );

	static const char *const names[] = { "alpha", "bravo", "charlie", "delta" };
	int i = 0;
	for ( auto &node : dict )
	{
		CHECK( i < 4 && strcmp( node.key, names[i] ) == 0 && node.elem == i + 1 );
		node.elem *= 10;
		++i;
	}
	CHECK( i == 4 );

	i = 0;
	const CUtlDict<int> &cdict = dict;
	for ( const auto &node : cdict )
	{
		CHECK( strcmp( node.key, names[i] ) == 0 && node.elem == ( i + 1 ) * 10 );
		++i;
	}
	CHECK( i == 4 );
}

static void TestHashtable()
{
	CUtlHashtable<int, int> table;
	CHECK( table.begin() == table.end() );

	for ( int v : s_Values )
		table.Insert( v, v * 10 );
	table.Remove( s_Values[2] );

	// Yields the pairs in the order FOR_EACH_HASHTABLE visits their handles
	auto it = table.begin();
	int nVisited = 0;
	FOR_EACH_HASHTABLE( table, h )
	{
		CHECK( it != table.end() && it.Handle() == h && it->m_key == table.Key( h ) && &it->m_value == &table[h] );
		++it;
		++nVisited;
	}
	CHECK( it == table.end() && nVisited == s_nValues - 1 );

	int nSum = 0;
	for ( auto &pair : table )
	{
		CHECK( pair.m_key != s_Values[2] && pair.m_value == pair.m_key * 10 );
		pair.m_value = -pair.m_key;
		nSum += pair.m_key;
	}
	CHECK( nSum == std::accumulate( s_Values, s_Values + s_nValues, 0 ) - s_Values[2] );

	const CUtlHashtable<int, int> &ctable = table;
	CUtlHashtable<int, int>::const_iterator cit = table.begin();
	CHECK( cit == ctable.begin() );
	nVisited = 0;
	for ( const auto &pair : ctable )
	{
		CHECK( pair.m_value == -pair.m_key );
		++nVisited;
	}
	CHECK( nVisited == s_nValues - 1 && std::distance( ctable.begin(), ctable.end() ) == s_nValues - 1 );

	CUtlHashtable<int> set;
	for ( int v : s_Values )
		set.Insert( v );
	nSum = 0;
	for ( const auto &pair : set )
		nSum += pair.m_key;
	CHECK( nSum == std::accumulate( s_Values, s_Values + s_nValues, 0 ) );

	table.RemoveAll();
	CHECK( table.begin() == table.end() );
}

static void TestStableHashtable()
{
	CUtlStableHashtable<int, int> table;
	CHECK( table.begin() == table.end() );

	for ( int v : s_Values )
		table.Insert( v, v * 10 );
	table.Remove( s_Values[2] );

	// Yields the pairs in insertion order
	int i = 0;
	for ( auto &pair : table )
	{
		if ( i == 2 )
			++i;
		CHECK( i < s_nValues && pair.m_key == s_Values[i] && pair.m_value == s_Values[i] * 10 );
		pair.m_value = -pair.m_key;
		++i;
	}
	CHECK( i == s_nValues );

	const CUtlStableHashtable<int, int> &ctable = table;
	int nVisited = 0;
	for ( const auto &pair : ctable )
	{
		CHECK( pair.m_value == -pair.m_key && ctable.Find( pair.m_key ) != ctable.InvalidHandle() );
		++nVisited;
	}
	CHECK( nVisited == s_nValues - 1 );
}

static void TestStringMap()
{
	CUtlStringMap<int> map;
	CHECK( map.begin() == map.end() );

	static const char *const names[] = { "charlie", "alpha", "delta", "bravo" };
	for ( int i = 0; i < 4; i++ )
		map[names[i]] = i + 1;
	map["ALPHA"] = 20;

	// Yields the strings in the order they were added, ALPHA being alpha
	int i = 0;
	for ( auto [pszKey, elem] : map )
	{
		CHECK( i < 4 && strcmp( pszKey, names[i] ) == 0 && elem == ( i == 1 ? 20 : i + 1 ) );
		elem = -i;
		++i;
	}
	CHECK( i == 4 );

	i = 0;
	const CUtlStringMap<int> &cmap = map;
	CUtlStringMap<int>::const_iterator cit = map.begin();
	CHECK( cit == cmap.begin() && cit.Index() == map.Find( names[0] ) );
	for ( auto item : cmap )
	{
		CHECK( item.key == cmap.String( i ) && item.elem == -i && &item.elem == &cmap[map.Find( names[i] )] );
		++i;
	}
	CHECK( i == 4 && std::distance( cmap.begin(), cmap.end() ) == 4 );

	map.Clear();
	CHECK( map.begin() == map.end() );
}

static void TestTSHash()
{
	CUtlTSHash<int, 8, int> hash( 16 );
	CHECK( hash.begin() == hash.end() );

	// More elements than buckets, so some share one
	for ( int i = 1; i <= 20; i++ )
		hash.Insert( i, i * 10 );
	hash.Commit();
	hash.FindAndRemove( 7 );

	int nSum = 0, nVisited = 0;
	for ( auto it = hash.begin(); it != hash.end(); ++it )
	{
		CHECK( *it == hash.GetID( it._index() ) * 10 && hash.Find( hash.GetID( it._index() ) ) == it._index() );
		*it = -*it;
		nSum += hash.GetID( it._index() );
		++nVisited;
	}
	CHECK( nVisited == 19 && nSum == 210 - 7 );

	const CUtlTSHash<int, 8, int> &chash = hash;
	nSum = 0;
	for ( const int &v : chash )
		nSum += v;
	CHECK( nSum == -( 2100 - 70 ) && std::distance( chash.begin(), chash.end() ) == chash.Count() );

	hash.RemoveAll();
	CHECK( hash.begin() == hash.end() );
}

static void TestHashMapLarge()
{
	CUtlHashMapLarge<int, int> map;
	CHECK( map.IterItems().begin() == map.IterItems().end() );

	// Enough elements to grow the buckets and rehash
	for ( int i = 1; i <= 40; i++ )
		map.Insert( i, i * 10 );
	map.Remove( 7 );

	// Keys, values and items walk the same valid indexes in order
	int nSum = 0, nVisited = 0;
	auto i = map.First();
	for ( auto item : map.IterItems() )
	{
		CHECK( item.Index() == i && item.Key() == map.Key( i ) && item.Element() == item.Key() * 10 );
		item.Element() = -item.Key();
		nSum += item.Key();
		++nVisited;
		i = map.Next( i );
	}
	CHECK( i == map.InvalidIndex() && nVisited == 39 && nSum == 820 - 7 );

	nSum = 0;
	for ( const int &k : map.IterKeys() )
		nSum += k;
	CHECK( nSum == 820 - 7 );

	for ( int &v : map.IterValues() )
		v *= 2;

	const CUtlHashMapLarge<int, int> &cmap = map;
	nSum = 0;
	for ( const int &v : cmap.IterValues() )
		nSum += v;
	for ( auto item : cmap.IterItems() )
		CHECK( item.Element() == -2 * item.Key() );
	CHECK( nSum == -2 * ( 820 - 7 ) );

	map.RemoveAll();
	CHECK( map.IterKeys().begin() == map.IterKeys().end() );
}

static void TestQueue()
{
	CUtlQueue<int> queue( 0, 8 );
	CHECK( queue.begin() == queue.end() );

	// Filling the allocation, removing from the head and adding more wraps the ring around
	for ( int i = 0; i < 8; i++ )
		queue.Insert( i );
	for ( int i = 0; i < 3; i++ )
		queue.RemoveAtHead();
	for ( int i = 8; i < 10; i++ )
		queue.Insert( i );

	static const int expected[] = { 3, 4, 5, 6, 7, 8, 9 };
	int i = 0;
	for ( const int &v : queue )
	{
		CHECK( i < 7 && v == expected[i] );
		++i;
	}
	CHECK( i == 7 && std::distance( queue.begin(), queue.end() ) == queue.Count() );
	CHECK( YieldsReversed( queue, expected, 7 ) );
	CHECK( *queue.begin() == queue.Head() && *std::prev( queue.end() ) == queue.Tail() );

	queue.RemoveAll();
	CHECK( queue.begin() == queue.end() );
}

// The FOR_EACH loops take the container's index type, so they also work with unsigned ones
static void TestUnsignedIndexLoops()
{
	CUtlDict<int, unsigned int> dict;
	dict.Insert( "bravo", 2 );
	dict.Insert( "alpha", 1 );
	dict.Insert( "charlie", 3 );

	int nSum = 0, nPrev = 0;
	FOR_EACH_DICT( dict, i )
	{
		CHECK( dict[i] > nPrev );
		nPrev = dict[i];
		nSum += dict[i];
	}
	CHECK( nSum == 6 );

	nSum = 0;
	FOR_EACH_DICT_FAST( dict, i )
		nSum += dict[i];
	CHECK( nSum == 6 );

	CUtlOrderedMap<int, int, CDefLess<int>, unsigned int> map;
	map.Insert( 2, 20 );
	map.Insert( 1, 10 );
	map.Insert( 3, 30 );

	nSum = 0, nPrev = 0;
	FOR_EACH_MAP( map, i )
	{
		CHECK( map.Key( i ) > nPrev );
		nPrev = map.Key( i );
		nSum += map[i];
	}
	CHECK( nSum == 60 );

	nSum = 0;
	FOR_EACH_MAP_FAST( map, i )
		nSum += map[i];
	CHECK( nSum == 60 );

	CUtlRBTree<int, unsigned int> tree;
	tree.Insert( 2 );
	tree.Insert( 1 );
	tree.Insert( 3 );

	nSum = 0, nPrev = 0;
	FOR_EACH_UTLRBTREE( tree, i )
	{
		CHECK( tree[i] > nPrev );
		nPrev = tree[i];
		nSum += tree[i];
	}
	CHECK( nSum == 6 );
}

// The vector and hash map loops take the container's index type too, wider or narrower than int
static void TestWideIndexLoops()
{
	CUtlVector<int, int64> vec;
	for ( int i = 1; i <= 4; i++ )
		vec.AddToTail( i );

	int nSum = 0, nPrev = 0;
	FOR_EACH_VEC( vec, i )
	{
		CHECK( sizeof( i ) == sizeof( int64 ) && vec[i] > nPrev );
		nPrev = vec[i];
		nSum += vec[i];
	}
	CHECK( nSum == 10 );

	nSum = 0, nPrev = 5;
	FOR_EACH_VEC_BACK( vec, i )
	{
		CHECK( sizeof( i ) == sizeof( int64 ) && vec[i] < nPrev );
		nPrev = vec[i];
		nSum += vec[i];
	}
	CHECK( nSum == 10 );

	CUtlVector<int, int64> copy;
	copy = vec;
	CHECK( copy.Count() == 4 && copy[ 0 ] == 1 && copy[ 3 ] == 4 );

	CUtlVectorFixedGrowable<int, 2, int64> fixed( 4 );
	for ( int i = 1; i <= 3; i++ )
		fixed.AddToTail( i );
	CHECK( fixed.Count() == 3 && fixed[ 2 ] == 3 );

	CUtlHashMap<int, int, CDefEquals<int>, DefaultHashFunctor<int>, short> map;
	map.Insert( 1, 10 );
	map.Insert( 2, 20 );
	map.Insert( 3, 30 );

	nSum = 0;
	FOR_EACH_HASHMAP( map, i )
	{
		CHECK( sizeof( i ) == sizeof( short ) );
		nSum += map[i];
	}
	CHECK( nSum == 60 );
}

int main()
{
	TestVectors();
	TestLinkedLists();
	TestRBTree();
	TestOrderedMap();
	TestDict();
	TestHashtable();
	TestStableHashtable();
	TestStringMap();
	TestTSHash();
	TestHashMapLarge();
	TestQueue();
	TestUnsignedIndexLoops();
	TestWideIndexLoops();

	if ( g_nFailures )
	{
		printf( "%d checks failed\n", g_nFailures );
		return 1;
	}

	printf( "All checks passed\n" );
	return 0;
}
