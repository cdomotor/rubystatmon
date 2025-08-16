# File: app/helpers/stations_helper.rb
# Path: /app/helpers/stations_helper.rb
module StationsHelper
  def pill_classes(active)
    base = "px-3 py-1.5 rounded-full text-sm font-medium border"
    active ? "#{base} bg-indigo-600 text-white border-indigo-600"
           : "#{base} bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
  end
end
