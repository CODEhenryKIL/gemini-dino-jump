-- Allow reviewed draw windows from 1 to 5,000 while preserving revision guards.
-- Keep all original pool rows, inventory and historical draw versions.
begin;
set local lock_timeout = '2s';
set local statement_timeout = '10s';
do $migration$
declare schema_name text;
begin
  foreach schema_name in array array['dino_dev','dino_prod'] loop
    if to_regclass(format('%I.draw_pool_slot', schema_name)) is null then continue; end if;
    execute format($ddl$
      create or replace function %I.enforce_draw_pool_policy()
      returns trigger language plpgsql security invoker set search_path = '' as $fn$
      declare policy jsonb; current_version text; draw_version text; ceiling integer;
      begin
        perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('draw-pool:' || NEW.campaign_id,0));
        execute format('select settings->''draw_pool_policy'',probability_version from %%I.campaign where id=$1',TG_TABLE_SCHEMA)
          into policy,current_version using NEW.campaign_id;
        if policy is null then return NEW; end if;
        if pg_catalog.jsonb_typeof(policy) <> 'object'
          or coalesce(policy->>'version','') = ''
          or policy->>'version' is distinct from current_version
          or pg_catalog.jsonb_typeof(policy->'active_slot_max') is distinct from 'number'
          or (policy->>'active_slot_max') !~ '^[0-9]+$'
          or pg_catalog.jsonb_typeof(policy->'initial_remaining') is distinct from 'number'
          or (policy->>'initial_remaining') !~ '^[0-9]+$' then
          raise exception 'Invalid draw pool policy' using errcode='23514';
        end if;
        ceiling := (policy->>'active_slot_max')::integer;
        if ceiling < 1 or ceiling > 5000
          or (policy->>'initial_remaining')::integer < 1
          or (policy->>'initial_remaining')::integer > 5000 then
          raise exception 'Invalid draw pool ceiling' using errcode='23514';
        end if;
        if TG_TABLE_NAME = 'draw' then
          if pg_catalog.current_setting('dino.draw_policy_version',true) is distinct from current_version
            or NEW.probability_version is distinct from current_version then
            raise exception 'Draw runtime policy revision mismatch' using errcode='23514';
          end if;
        elsif OLD.allocated_draw_id is null and NEW.allocated_draw_id is not null then
          if NEW.slot_number > ceiling then
            raise exception 'Draw slot is outside the active pool' using errcode='23514';
          end if;
          execute format('select probability_version from %%I.draw where id=$1 and campaign_id=$2',TG_TABLE_SCHEMA)
            into draw_version using NEW.allocated_draw_id,NEW.campaign_id;
          if draw_version is distinct from current_version then
            raise exception 'Draw allocation policy revision mismatch' using errcode='23514';
          end if;
        end if;
        return NEW;
      end;
      $fn$;
    $ddl$,schema_name);
    execute format('revoke all on function %I.enforce_draw_pool_policy() from public',schema_name);
    execute format('grant execute on function %I.enforce_draw_pool_policy() to %I',schema_name,schema_name||'_app');
    execute format('drop trigger if exists draw_pool_policy_insert on %I.draw',schema_name);
    execute format('create trigger draw_pool_policy_insert before insert on %I.draw for each row execute function %I.enforce_draw_pool_policy()',schema_name,schema_name);
    execute format('drop trigger if exists draw_pool_policy_allocation on %I.draw_pool_slot',schema_name);
    execute format('create trigger draw_pool_policy_allocation before update of allocated_draw_id on %I.draw_pool_slot for each row execute function %I.enforce_draw_pool_policy()',schema_name,schema_name);
    execute format('insert into %I.schema_version(version) values(''20261001023302'') on conflict(version) do nothing',schema_name);
  end loop;
end
$migration$;
commit;
