#!/usr/bin/env ruby
# Render without cluster access and check the takeover's important invariants.
require 'yaml'
require 'open3'

Dir.chdir(File.expand_path('..', __dir__))
chart = ARGV.fetch(0) { abort 'Usage: ruby hack/check-trustify.rb /path/to/charts/trustify' }

def check(condition, message)
  abort message unless condition
end

def render(*command)
  stdout, stderr, status = Open3.capture3(*command)
  abort stderr unless status.success?
  YAML.load_stream(stdout).compact
end

values = YAML.load_file('deploy/trustify/values.yaml')
image = values.fetch('image').fetch('fullName')
check(image.match?(/\Aghcr\.io\/guacsec\/trustd@sha256:[a-f0-9]{64}\z/), 'Application image must use an upstream digest')
%w[createDatabase createImporters].each do |name|
  check(values.fetch('modules').fetch(name).fetch('enabled') == false, "#{name} must stay disabled")
end

app = render('helm', 'template', 'trustify', chart, '-n', 'trustify', '-f', 'deploy/trustify/values.yaml')
check(app.none? { |r| r['kind'] == 'Secret' }, 'Chart must not generate Secrets')
check(app.select { |r| r['kind'] == 'Job' }.map { |r| r.dig('metadata', 'name') } == ['migrate-db'], 'Only the non-destructive migration hook may recur')
app.select { |r| %w[Deployment Job].include?(r['kind']) }.each do |resource|
  resource.fetch('spec').fetch('template').fetch('spec').fetch('containers').each do |container|
    check(container['image'] == image, 'Application and migration images must match')
    container.fetch('env', []).each do |env|
      next unless env['name'].match?(/PASSWORD|SECRET_KEY|ACCESS_KEY|CLIENT_SECRET/)
      check(env.dig('valueFrom', 'secretKeyRef'), "#{env['name']} must reference a cluster Secret")
    end
  end
end
server = app.find { |r| r['kind'] == 'Deployment' && r.dig('metadata', 'name') == 'server' }
check(server.dig('spec', 'template', 'spec', 'containers', 0, 'env').include?({
  'name' => 'CLIENT_TLS_CA_CERTIFICATES',
  'value' => '/run/secrets/kubernetes.io/serviceaccount/service-ca.crt'
}), 'OpenShift service CA must be configured')

platform = render('oc', 'kustomize', 'deploy/trustify/platform')
check(platform.map { |r| r['kind'] }.sort == %w[Ingress OpenTelemetryCollector ServiceMonitor TempoStack].sort, 'Only operator inputs and manual ingress/monitoring belong to platform')
check(platform.none? { |r| r.dig('metadata', 'ownerReferences') }, 'Do not adopt operator-generated resources')

seed = render('helm', 'template', 'trustify', chart, '-n', 'trustify',
              '-f', 'deploy/trustify/values.yaml', '-f', 'operations/trustify/importers.yaml',
              '--show-only', 'templates/init/create-importers/020-Job.yaml')
check(seed.length == 1 && seed[0].dig('metadata', 'name') == 'create-importers', 'Seed overlay must render one explicit job')
check(seed[0].dig('spec', 'template', 'spec', 'containers', 0, 'image') == 'docker.io/library/postgres:17.9', 'Seed job needs psql rather than the application image')
inspect_job = YAML.load_file('operations/trustify/database.yaml')
env = inspect_job.dig('spec', 'template', 'spec', 'containers', 0, 'env')
check(env.find { |e| e['name'] == 'RESET_MODE' }['value'] == 'inspect', 'Database operation must default to read-only inspection')
%w[argocd/trustify-application.yaml argocd/trustify-platform-application.yaml].each do |path|
  application = YAML.load_file(path)
  check(!application.dig('metadata', 'finalizers'), 'Application deletion must not cascade')
  check(application.dig('spec', 'syncPolicy', 'automated', 'prune') != true, 'Pruning must stay disabled')
end
puts 'Trustify rendering, image, credential-reference, hook, and ownership checks passed.'
