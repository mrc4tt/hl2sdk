#ifndef VECTORWS_H
#define VECTORWS_H

#ifdef _WIN32
#pragma once
#endif

#include "vector.h"

// AMNOTE: Mostly a stub over a real VectorWS,
// most likely meaning of it is world space vector
class VectorWS : public Vector
{
public:
	using Vector::Vector;

	// A using-declaration never inherits the base's copy constructor, so
	// VectorWS( someVector ) - which variant.h does with vec3_origin - needs
	// this one spelled out, and declaring it takes the implicit default away.
	VectorWS() = default;
	VectorWS( const Vector &v ) : Vector( v ) {}
};

class QuaternionWS : public Quaternion
{
public:
	using Quaternion::Quaternion;
};

#endif // VECTORWS_H