json.extract! station, :id, :name, :ip_address, :location, :notes, :created_at, :updated_at
json.url station_url(station, format: :json)
