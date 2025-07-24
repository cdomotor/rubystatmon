# Fix for tzinfo not working on Windows (no zoneinfo database)
require 'tzinfo'

TZInfo::DataSource.set(TZInfo::DataSources::RubyDataSource.new)
