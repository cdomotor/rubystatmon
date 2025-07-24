require 'csv'

class StationImporter
  def self.import(file_path)
    CSV.foreach(file_path, headers: true) do |row|
      Station.find_or_create_by!(ip_address: row['ip_address']) do |station|
        station.name = row['name']
        station.location = row['location']
        station.notes = row['notes']
      end
    end
  end
end
