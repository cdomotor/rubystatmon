# File: app/services/stations/csv_import.rb
# Path: /app/services/stations/csv_import.rb
require "csv"
module Stations
  class CsvImport
    # Supported headers (case-insensitive)
    HEADERS = %w[
      id name ip_address active filestore_path ingest_enabled ingest_parameters tags
    ].freeze

    def initialize(csv_string, create_missing:, update_existing:)
      @csv_string      = csv_string
      @create_missing  = !!create_missing
      @update_existing = !!update_existing
    end

    # Returns a Hash report:
    # {
    #   rows: [ { index:, attrs:, action:, ok:, errors: [] }, ... ],
    #   totals: { creates:, updates:, skipped:, errors: }
    # }
    def run(dry_run: true)
      rows = []
      creates = updates = skipped = errors = 0

      each_row do |idx, attrs|
        action, ok, errs = process_row(attrs, dry_run:)
        rows << { index: idx, attrs:, action:, ok:, errors: errs }
        case action
        when :create then creates += 1
        when :update then updates += 1
        when :skip   then skipped += 1
        end
        errors += 1 if !ok && errs.present?
      end

      { rows:, totals: { creates:, updates:, skipped:, errors: } }
    end

    private

    def each_row
      csv = CSV.new(@csv_string, headers: true, return_headers: false)
      csv.each_with_index do |row, i|
        next if row.to_h.values.all?(&:blank?) # skip empty lines
        attrs = normalize_attrs(row.to_h)
        yield(i + 2, attrs) # +2 for header + 1-based line number
      end
    end

    def process_row(attrs, dry_run:)
      errs = []
      station = find_target(attrs)

      if station.nil?
        unless @create_missing
          return [:skip, true, []] # skipping is "ok"
        end
        station = Station.new
        assign(station, attrs)
        return [:create, valid_save(station, errs, dry_run:), errs]
      else
        unless @update_existing
          return [:skip, true, []]
        end
        assign(station, attrs)
        return [:update, valid_save(station, errs, dry_run:), errs]
      end
    rescue => e
      return [:skip, false, [e.message]]
    end

    def valid_save(station, errs, dry_run:)
      if station.valid?
        if dry_run
          true
        else
          station.save!
          true
        end
      else
        errs.concat(station.errors.full_messages)
        false
      end
    rescue => e
      errs << e.message
      false
    end

    def find_target(attrs)
      # Priority: id > name > ip_address
      if attrs[:id].present?
        return Station.where(id: attrs[:id]).first
      end
      if attrs[:name].present?
        return Station.where("LOWER(name) = ?", attrs[:name].downcase).first
      end
      if attrs[:ip_address].present?
        return Station.where(ip_address: attrs[:ip_address]).first
      end
      nil
    end

    def assign(station, attrs)
      station.name           = attrs[:name]           if attrs.key?(:name)
      station.ip_address     = attrs[:ip_address]     if attrs.key?(:ip_address)
      station.active         = attrs[:active]         if has_column?(:stations, :active) && attrs.key?(:active)
      station.filestore_path = attrs[:filestore_path] if has_column?(:stations, :filestore_path) && attrs.key?(:filestore_path)
      station.ingest_enabled = attrs[:ingest_enabled] if has_column?(:stations, :ingest_enabled) && attrs.key?(:ingest_enabled)

      if attrs.key?(:ingest_parameters) && !attrs[:ingest_parameters].nil?
        # Model already casts JSON, but we normalize here too
        ip = attrs[:ingest_parameters]
        station.ingest_parameters = normalize_ingest_params(ip)
      end

      if has_column?(:stations, :tags) && attrs.key?(:tags)
        station.tags = normalize_tags(attrs[:tags])
      end
    end

    # ---------- Normalization helpers ----------

    def normalize_attrs(h)
      out = {}
      h.each do |k, v|
        key = k.to_s.strip.downcase
        next unless HEADERS.include?(key)
        val = v.is_a?(String) ? v.strip : v

        case key
        when "id"
          out[:id] = (val.present? ? Integer(val) rescue nil : nil)
        when "name", "ip_address", "filestore_path"
          out[key.to_sym] = (val.presence)
        when "active", "ingest_enabled"
          out[key.to_sym] = truthy?(val)
        when "ingest_parameters"
          out[:ingest_parameters] = (val.presence)
        when "tags"
          out[:tags] = (val.presence)
        end
      end
      out
    end

    def truthy?(v)
      return v if v == true || v == false
      %w[1 true yes y on].include?(v.to_s.strip.downcase)
    end

    def normalize_tags(str)
      return "" if str.blank?
      str.split(/[,;\s]+/).map(&:strip).reject(&:blank?).uniq.join(",")
    end

    # Accept either JSON string like:
    #   {"Battery":{"trend_days":7},"Flow":{"trend_days":3}}
    # or a simple "Battery:7; Flow:3"
    def normalize_ingest_params(val)
      return {} if val.blank?
      if val.is_a?(Hash)
        return stringify_and_coerce(val)
      end
      # Try JSON first
      begin
        obj = JSON.parse(val)
        return stringify_and_coerce(obj) if obj.is_a?(Hash)
      rescue JSON::ParserError
      end
      # Try simple "Param:7;Other:3"
      hash = {}
      val.to_s.split(/[,;]+/).each do |token|
        name, days = token.split(":").map(&:strip)
        next if name.blank?
        td = (Integer(days) rescue nil)
        hash[name] = { "trend_days" => (td && td > 0 ? td : nil) }
      end
      hash
    end

    def stringify_and_coerce(h)
      h.each_with_object({}) do |(k, v), acc|
        td = (v || {})["trend_days"] || (v || {})[:trend_days]
        acc[k.to_s] = { "trend_days" => (Integer(td) rescue nil) }
      end
    end

    # Schema guard (so this works before migrations land)
    def has_column?(table, column)
      @__cols ||= {}
      @__cols[table] ||= begin
        cols = ActiveRecord::Base.connection.columns(table).map(&:name).map(&:to_s)
        cols.index_by { |c| c }
      rescue
        {}
      end
      @__cols[table].key?(column.to_s)
    end
  end
end
