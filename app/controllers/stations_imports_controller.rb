# File: app/controllers/stations_imports_controller.rb
# Path: /app/controllers/stations_imports_controller.rb
class StationsImportsController < ApplicationController
  require "base64"

  # GET /stations/import
  def new
  end

  # POST /stations/import/preview
  def preview
    unless params[:csv].respond_to?(:read)
      redirect_to stations_import_path, alert: "Please choose a CSV file." and return
    end

    csv_raw = params[:csv].read
    options = {
      create_missing: ActiveModel::Type::Boolean.new.cast(params[:create_missing]),
      update_existing: ActiveModel::Type::Boolean.new.cast(params[:update_existing]),
    }

    report = Stations::CsvImport.new(csv_raw, **options).run(dry_run: true)

    @report = report
    @options = options
    @payload_b64 = Base64.strict_encode64(csv_raw) # pass file to commit step safely
  end

  # POST /stations/import/commit
  def commit
    payload = Base64.decode64(params[:payload_b64].to_s)
    options = {
      create_missing: ActiveModel::Type::Boolean.new.cast(params[:create_missing]),
      update_existing: ActiveModel::Type::Boolean.new.cast(params[:update_existing]),
    }

    report = Stations::CsvImport.new(payload, **options).run(dry_run: false)
    @report = report
  end

  # GET /stations/import/template
  def template
    sample = <<~CSV
      id,name,ip_address,active,filestore_path,ingest_enabled,ingest_parameters,tags
      ,Station A,10.0.0.10,true,\\\\server\\share\\A,true,{"Battery":{"trend_days":7}},"river, north"
      ,Station B,10.0.0.11,true,C:\\\\data\\\\logger\\\\B,false,{},""
      6,Existing by ID,10.0.0.12,,\\\\server\\share\\E,,{"Flow":{"trend_days":3}},"updated"
    CSV
    send_data sample, filename: "stations_import_template.csv", type: "text/csv"
  end
end
