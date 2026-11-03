//===== Copyright © 1996-2005, Valve Corporation, All rights reserved. ======//
//
// Purpose: 
//
//===========================================================================//

#ifndef UTLSTRINGMAP_H
#define UTLSTRINGMAP_H
#ifdef _WIN32
#pragma once
#endif

#include "utlsymboltable.h"

#include <iterator>

template <class T>
class CUtlStringMap
{
public:
	CUtlStringMap( bool caseInsensitive = true, int initsize = 32 ) : 
	  m_Vector( initsize ),
		  m_SymbolTable( 0, 32, caseInsensitive )
	{
	}

	// Get data by the string itself:
	T& operator[]( const char *pString )
	{
		CUtlSymbol symbol = m_SymbolTable.AddString( pString );
		int index = ( int )( UtlSymId_t )symbol;
		if( m_Vector.Count() <= index )
		{
			m_Vector.EnsureCount( index + 1 );
		}
		return m_Vector[index];
	}

	// Get data by the string's symbol table ID - only used to retrieve a pre-existing symbol, not create a new one!
	T& operator[]( UtlSymId_t n )
	{
		Assert( n <= m_Vector.Count() );
		return m_Vector[n];
	}

	const T& operator[]( UtlSymId_t n ) const
	{
		Assert( n <= m_Vector.Count() );
		return m_Vector[n];
	}

	bool Defined( const char *pString ) const
	{
		return m_SymbolTable.Find( pString ).IsValid();
	}

	UtlSymId_t Find( const char *pString ) const
	{
		return m_SymbolTable.Find( pString );
	}

	UtlSymId_t AddString( const char *pString, bool* created = NULL )
	{
		CUtlSymbol symbol = m_SymbolTable.AddString( pString, created );
		int index = ( int )( UtlSymId_t )symbol;
		if( m_Vector.Count() <= index )
		{
			m_Vector.EnsureCount( index + 1 );
		}
		return symbol;
	}

	static UtlSymId_t InvalidIndex()
	{
		return UTL_INVAL_SYMBOL;
	}

	int GetNumStrings( void ) const
	{
		return m_SymbolTable.GetNumStrings();
	}

	const char *String( int n )	const
	{
		return m_SymbolTable.String( n );
	}

	// Clear all of the data from the map
	void Clear()
	{
		m_Vector.RemoveAll();
		m_SymbolTable.RemoveAll();
	}

	void Purge()
	{
		m_Vector.Purge();
		m_SymbolTable.RemoveAll();
	}

	void PurgeAndDeleteElements()
	{
		m_Vector.PurgeAndDeleteElements();
		m_SymbolTable.RemoveAll();
	}

	// STL / C++11-style iterators over the strings in the order they were added, with the string in key and its data
	// in elem, also as for ( auto [pszKey, elem] : map )
	template <bool bConstIterator>
	class IteratorT
	{
	public:
		typedef typename CTypeSelect<bConstIterator, const CUtlStringMap, CUtlStringMap>::type Map_t;

		struct Item_t
		{
			const char *key;
			typename CTypeSelect<bConstIterator, const T, T>::type &elem;
		};

		typedef std::forward_iterator_tag iterator_category;
		typedef Item_t value_type;
		typedef void pointer;
		typedef Item_t reference;
		typedef intp difference_type;

		IteratorT() {}
		IteratorT( Map_t *pMap, int nString ) : m_pMap( pMap ), m_nString( nString ) {}
		IteratorT( const IteratorT<false> &copy_or_requalify_to_const ) : m_pMap( copy_or_requalify_to_const.m_pMap ), m_nString( copy_or_requalify_to_const.m_nString ) {}

		IteratorT &operator++() { ++m_nString; return *this; }
		IteratorT operator++( int ) { IteratorT pre = *this; ++m_nString; return pre; }

		template <bool bOtherConst> bool operator==( const IteratorT<bOtherConst> &other ) const { return m_nString == other.m_nString; }
		template <bool bOtherConst> bool operator!=( const IteratorT<bOtherConst> &other ) const { return m_nString != other.m_nString; }

		Item_t operator*() const { return { m_pMap->String( m_nString ), ( *m_pMap )[ (UtlSymId_t)m_nString ] }; }

		// The string's symbol table ID
		UtlSymId_t Index() const { return (UtlSymId_t)m_nString; }

	private:
		template <bool> friend class IteratorT;

		Map_t *m_pMap = nullptr;
		int m_nString = 0;
	};
	typedef IteratorT<false> iterator;
	typedef IteratorT<true> const_iterator;
	iterator begin() { return iterator( this, 0 ); }
	const_iterator begin() const { return const_iterator( this, 0 ); }
	iterator end() { return iterator( this, GetNumStrings() ); }
	const_iterator end() const { return const_iterator( this, GetNumStrings() ); }



private:
	CUtlVector<T> m_Vector;
	CUtlSymbolTable m_SymbolTable;
};

#endif // UTLSTRINGMAP_H
