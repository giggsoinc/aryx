#!/bin/bash
# Load support demo schema + data into Aryx PostgreSQL on EC2

set -e

# Configuration (adjust as needed)
DB_HOST=${ARYX_DB_HOST:-localhost}
DB_PORT=${ARYX_DB_PORT:-5432}
DB_NAME=${ARYX_DB_NAME:-aryx}
DB_USER=${ARYX_DB_USER:-aryx}
DB_PASSWORD=${ARYX_DB_PASSWORD:-aryx}

SCHEMA_FILE="migrations/002_support_demo_schema.sql"

echo "🔧 Loading Aryx support demo schema..."
echo "   Host: $DB_HOST:$DB_PORT / Database: $DB_NAME"

# Apply schema
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SCHEMA_FILE"

echo "✅ Schema loaded successfully."
echo ""
echo "📍 Next step: Start the Aryx API server and hit:"
echo "   POST http://localhost:8000/api/demo/load"
echo "   Body: {\"ticket_count\": 200, \"clean_first\": true}"
echo ""
echo "Or use curl:"
echo "   curl -X POST http://localhost:8000/api/demo/load \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"ticket_count\": 200, \"clean_first\": true}'"
